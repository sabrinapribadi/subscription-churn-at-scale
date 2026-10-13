"""P6 on Databricks: retrain the champion, check parity with the local build, register it (ADR-008).

Runs as the second task of the bundle job (databricks.yml), after build_dataset.py has written the
k = 14, W = 30 features to the data volume. Same recipe as P4 (scripts/rank_and_calibrate.py):
LightGBM on February 2017, isotonic + prior-shift calibration, tested on March 2017, call list
ordered by probability × member value. The model is registered in Unity Catalog and gets the
`champion` alias only if every parity check passes.

    python scripts/databricks_train_register.py            # on Databricks (job task)
"""

from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT, load_config  # noqa: E402
from src.evaluation.metrics import evaluate  # noqa: E402
from src.models.baseline import NON_FEATURES, PARAMS, fit, holdout_split, prepare  # noqa: E402
from src.models.ranking import fit_isotonic, member_value, prior_shift_em, profit_at  # noqa: E402

TRAIN, TEST, K = 201702, 201703, 14


def load(path: Path) -> pd.DataFrame:
    df = ds.dataset(str(path), format="parquet", partitioning=None).to_table().to_pandas()  # cohort is a column in the files
    df["cohort"] = df["cohort"].astype(int)
    return df


def feature_parity(ours: pd.DataFrame, ref: pd.DataFrame, feats: list[str]) -> dict:
    """Join on member and cohort; a row matches when every feature is equal (relative 1e-6, missing == missing)."""
    m = ours.merge(ref, on=["msno", "cohort"], suffixes=("", "__ref"), how="outer", indicator=True)
    both = m[m["_merge"] == "both"]
    ok = np.ones(len(both), dtype=bool)
    worst = {}
    for f in feats + ["label", "snapshot", "last_expire"]:
        a = pd.to_numeric(both[f].astype("float64"), errors="coerce").to_numpy()
        b = pd.to_numeric(both[f"{f}__ref"].astype("float64"), errors="coerce").to_numpy()
        same = (np.isnan(a) & np.isnan(b)) | np.isclose(a, b, rtol=1e-6, atol=1e-9, equal_nan=True)
        ok &= same
        if not same.all():
            worst[f] = int((~same).sum())
    return {"members_ours": int(len(ours)), "members_reference": int(len(ref)), "only_ours": int((m["_merge"] == "left_only").sum()),
            "only_reference": int((m["_merge"] == "right_only").sum()), "rows_identical": float(ok.mean()) if len(ok) else 0.0,
            "features_with_differences": worst}


def main() -> None:
    import mlflow
    from databricks.sdk import WorkspaceClient
    from mlflow.models import infer_signature

    t_start = time.time()
    cfg = load_config()
    P, D, biz, frac = cfg["paths"], cfg["databricks"], cfg["business"], cfg["validation"]["top_k_fraction"]
    W = cfg["framing"]["window_days_selected"]
    ref_p4 = json.loads((ROOT / "data" / "outputs" / "p4_rank_calibrate.json").read_text())

    # ---- features built on Databricks by task 1, and the local reference
    data = prepare(load(Path(P["features_dir"]) / f"k{K}_w{W}"))
    feats = [c for c in data.columns if c not in NON_FEATURES]
    ref = prepare(load(Path(P["reference_dir"]) / f"k{K}_w{W}"))
    parity = feature_parity(data, ref, feats); del ref; gc.collect()
    print("feature parity", json.dumps(parity), flush=True)

    data["member_value"] = member_value(data, biz["value_horizon_days"])
    train = data[data["cohort"] == TRAIN].reset_index(drop=True)
    test = data[data["cohort"] == TEST].reset_index(drop=True)
    del data; gc.collect()
    y_tr, y_te, v_te = train["label"].to_numpy(), test["label"].to_numpy(), test["member_value"].to_numpy()

    # ---- same recipe as P4
    t0 = time.time()
    clf = fit(train, feats)
    tr_idx, va_idx = holdout_split(train)
    p_raw = clf.predict_proba(test[feats])[:, 1]
    iso = fit_isotonic(clf.predict_proba(train.iloc[va_idx][feats])[:, 1], y_tr[va_idx])
    prior_train = float(y_tr[tr_idx].mean())
    p_em, pi_hat = prior_shift_em(iso.predict(p_raw), prior_train)
    score = p_em + 1e-9 * p_raw  # tie-break as in P4
    train_seconds = round(time.time() - t0)
    clf_metrics = evaluate(y_te, score, frac)
    profit_ev = profit_at(score * v_te, y_te, v_te, frac, biz["save_rate"], biz["contact_cost"])

    # ---- gate (ADR-008)
    tol, ref_s, ref_c = cfg["parity"], ref_p4["setup"], ref_p4["classifier"]
    ref_profit = ref_p4["central"]["expected_value"]["profit"]
    checks = {
        "same_members_and_churners": int(len(test)) == ref_s["test_members"] and int(y_te.sum()) == ref_s["test_churners"],
        "features_match_local": parity["only_ours"] == 0 and parity["only_reference"] == 0
                                and parity["rows_identical"] >= tol["feature_rows_identical_min"],
        "pr_auc_reproduced": abs(clf_metrics["pr_auc"] - ref_c["pr_auc"]) <= tol["pr_auc_abs_tol"],
        "churners_reached_reproduced": abs(clf_metrics["recall_at_k"] - ref_c["recall_at_k"]) <= tol["churners_reached_abs_tol"],
        "profit_reproduced": abs(profit_ev["profit"] - ref_profit) / ref_profit <= tol["profit_rel_tol"],
    }
    report = {
        "setup": {"train": TRAIN, "test": TEST, "lead_days": K, "window_days": W, "train_members": int(len(train)),
                  "test_members": int(len(test)), "test_churners": int(y_te.sum()), "best_iteration": int(clf.best_iteration_)},
        "feature_parity": parity,
        "databricks": {"pr_auc": clf_metrics["pr_auc"], "roc_auc": clf_metrics["roc_auc"], "churners_reached": clf_metrics["recall_at_k"],
                       "profit_expected_value": profit_ev["profit"], "estimated_march_rate": pi_hat},
        "local_p4": {"pr_auc": ref_c["pr_auc"], "roc_auc": ref_c["roc_auc"], "churners_reached": ref_c["recall_at_k"],
                     "profit_expected_value": ref_profit, "estimated_march_rate": ref_p4["calibration"]["estimated_march_rate"]},
        "checks": checks, "gate_passed": all(checks.values()), "train_seconds": train_seconds,
    }

    # ---- MLflow: log the run, register the model, alias it only if the gate passed
    w = WorkspaceClient()
    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(f"/Users/{w.current_user.me().user_name}/{D['experiment']}")
    with mlflow.start_run(run_name=f"p6-k{K}w{W}") as run:
        mlflow.log_params({**{k: v for k, v in PARAMS.items() if k != "verbose"}, "lead_days": K, "window_days": W,
                           "train_cohort": TRAIN, "test_cohort": TEST, "best_iteration": int(clf.best_iteration_)})
        mlflow.log_metrics({"pr_auc": clf_metrics["pr_auc"], "roc_auc": clf_metrics["roc_auc"],
                            "churners_reached_top10": clf_metrics["recall_at_k"], "profit_ev_top10": profit_ev["profit"],
                            "feature_rows_identical": parity["rows_identical"], "estimated_march_rate": pi_hat})
        mlflow.log_dict({"iso_x": [float(x) for x in iso.X_thresholds_], "iso_y": [float(y) for y in iso.y_thresholds_],
                         "prior_train": prior_train, "prior_new": float(pi_hat), "features": feats}, "calibration.json")
        mlflow.log_dict(report, "p6_parity.json")
        sample = test[feats].head(50)
        plain = sample.apply(lambda s: s.astype("float64") if s.dtype.name == "category" else s)  # signatures have no category type
        info = mlflow.lightgbm.log_model(clf, name="model", input_example=plain,
                                         signature=infer_signature(plain, clf.predict_proba(sample)[:, 1]),
                                         registered_model_name=D["model_name"])
        mlflow.set_tags({"gate_passed": str(report["gate_passed"]), "phase": "P6"})
    version = info.registered_model_version
    loaded = mlflow.lightgbm.load_model(f"models:/{D['model_name']}/{version}")
    report["registry"] = {"model": D["model_name"], "version": int(version), "run_id": run.info.run_id,
                          "reload_scores_identical": bool(np.allclose(loaded.predict_proba(test[feats].head(10_000))[:, 1], p_raw[:10_000]))}
    report["checks"]["registered_model_reloads"] = report["registry"]["reload_scores_identical"]
    report["gate_passed"] = all(report["checks"].values())
    if report["gate_passed"]:
        mlflow.MlflowClient().set_registered_model_alias(D["model_name"], D["alias"], version)
        report["registry"]["alias"] = D["alias"]
    report["total_seconds"] = round(time.time() - t_start)

    out = Path(P["outputs_dir"]); out.mkdir(parents=True, exist_ok=True)
    (out / "p6_parity.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    if not report["gate_passed"]:
        sys.exit("P6 gate failed: " + ", ".join(k for k, v in report["checks"].items() if not v))


if __name__ == "__main__":
    main()
