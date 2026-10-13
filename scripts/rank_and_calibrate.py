"""Phase 4: honest scores and a call list ordered by money at stake (ADR-004).

Base = P2 model (k = 14, W = 30), train Feb-2017 → test Mar-2017 (official labels).
1. Calibration: raw → isotonic (Feb hold-out) → + prior-shift EM on unlabelled March scores.
2. Ranking: probability sort vs expected-value sort (p × value) vs LambdaMART.
3. Profit at 10% over a save-rate × contact-cost grid; gates G1 and G2.

    python scripts/rank_and_calibrate.py
"""

from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

import mlflow
import numpy as np
import pyarrow.dataset as ds
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluation.metrics import evaluate  # noqa: E402
from src.models.baseline import canonical_rows, feature_columns, fit, holdout_split, prepare  # noqa: E402
from src.models.ranking import (ece, fit_isotonic, fit_lambdamart, member_value, prior_shift_em,  # noqa: E402
                                profit_at, profit_curve, relevance, value_curve)

TRAIN, TEST, K = 201702, 201703, 14
ECE_GATE = 0.010


def calib_summary(y, p):
    order = np.argsort(p)
    top = order[-len(p) // 10:]
    return {"ece": ece(y, p), "brier": float(np.mean((p - y) ** 2)), "mean_predicted": float(p.mean()),
            "actual_rate": float(y.mean()), "top_group_predicted": float(p[top].mean()), "top_group_observed": float(y[top].mean())}


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    biz, frac, W = cfg["business"], cfg["validation"]["top_k_fraction"], cfg["framing"]["window_days_selected"]
    # same build as the Databricks job (scripts/build_dataset.py --W 30), features in a fixed order (ADR-008)
    data = canonical_rows(prepare(ds.dataset(Path(cfg["paths"]["features_dir"]).expanduser() / f"k{K}_w{W}", format="parquet",
                                             partitioning=None).to_table().to_pandas()))
    feats = feature_columns(data)
    train = data[data["cohort"] == TRAIN].reset_index(drop=True)
    test = data[data["cohort"] == TEST].reset_index(drop=True)
    del data; gc.collect()
    for df in (train, test):
        df["member_value"] = member_value(df, cfg["business"]["value_horizon_days"])
    y_tr, y_te, v_te = train["label"].to_numpy(), test["label"].to_numpy(), test["member_value"].to_numpy()
    out = {"setup": {"train": TRAIN, "test": TEST, "lead_days": K, "window_days": W, "top_k_fraction": frac,
                     "save_rate": biz["save_rate"], "contact_cost": biz["contact_cost"], "value_horizon_days": biz["value_horizon_days"],
                     "test_members": int(len(test)), "test_churners": int(y_te.sum()), "test_value_at_risk": float((y_te * v_te).sum())}}

    # ---- 1. classifier + calibration
    t0 = time.time()
    clf = fit(train, feats)
    tr_idx, va_idx = holdout_split(train)
    p_va = clf.predict_proba(train.iloc[va_idx][feats])[:, 1]
    p_raw = clf.predict_proba(test[feats])[:, 1]
    iso = fit_isotonic(p_va, y_tr[va_idx])
    p_iso = iso.predict(p_raw)
    prior_train = float(y_tr[tr_idx].mean())
    p_em, pi_hat = prior_shift_em(p_iso, prior_train)
    out["calibration"] = {"train_churn_rate": prior_train, "estimated_march_rate": pi_hat, "actual_march_rate": float(y_te.mean()),
                          "raw": calib_summary(y_te, p_raw), "isotonic": calib_summary(y_te, p_iso), "isotonic_plus_em": calib_summary(y_te, p_em)}
    out["calibration"]["gate_G2_passed"] = bool(out["calibration"]["isotonic_plus_em"]["ece"] <= ECE_GATE)
    # Isotonic output is a step function: break ties with the raw score so ordering is not arbitrary.
    tie = 1e-9 * p_raw
    out["classifier"] = evaluate(y_te, p_em + tie, frac)
    print(f"classifier + calibration {time.time() - t0:.0f}s · estimated March churn {pi_hat:.4f} (actual {y_te.mean():.4f}) · "
          f"ECE raw {out['calibration']['raw']['ece']:.4f} → isotonic {out['calibration']['isotonic']['ece']:.4f} → +EM {out['calibration']['isotonic_plus_em']['ece']:.4f}", flush=True)
    # calibration curve for the page (10 equal groups)
    order = np.argsort(p_em)
    out["calibration"]["curve"] = [[float(p_em[c].mean()), float(y_te[c].mean())] for c in np.array_split(order, 10)]

    # ---- 2. LambdaMART
    t0 = time.time()
    churn_vals = train.loc[train["label"] == 1, "member_value"]
    cuts = (float(churn_vals.quantile(1 / 3)), float(churn_vals.quantile(2 / 3)))
    tr, va = train.iloc[tr_idx], train.iloc[va_idx]
    rank_feats = feats + ["member_value"]
    ranker = fit_lambdamart(tr, va, rank_feats, relevance(tr["label"].to_numpy(), tr["member_value"].to_numpy(), cuts),
                            relevance(va["label"].to_numpy(), va["member_value"].to_numpy(), cuts))
    s_rank = ranker.predict(test[rank_feats])
    out["lambdamart"] = {"value_tercile_cuts": cuts, "best_iteration": int(ranker.best_iteration_), "seconds": round(time.time() - t0)}
    print(f"LambdaMART trained in {time.time() - t0:.0f}s (best iteration {ranker.best_iteration_})", flush=True)

    # ---- 3. profit comparison
    rankers = {"probability": p_em + tie, "expected_value": (p_em + tie) * v_te, "lambdamart": s_rank}
    out["profit_grid"] = []
    for s in biz["save_rate_grid"]:
        for c in biz["contact_cost_grid"]:
            row = {"save_rate": s, "contact_cost": c}
            for name, sc in rankers.items():
                row[name] = profit_at(sc, y_te, v_te, frac, s, c)
            out["profit_grid"].append(row)
    central = next(r for r in out["profit_grid"] if r["save_rate"] == biz["save_rate"] and r["contact_cost"] == biz["contact_cost"])
    out["central"] = central
    out["gate_G1_passed"] = bool(central["lambdamart"]["profit"] > central["probability"]["profit"])
    best = max(rankers, key=lambda n: central[n]["profit"])
    ev_wins_tie = central["expected_value"]["profit"] >= central["lambdamart"]["profit"]
    out["recommendation"] = "expected_value" if ev_wins_tie and best != "probability" else best
    out["curves"] = {n: profit_curve(sc, y_te, v_te, biz["save_rate"], biz["contact_cost"]) for n, sc in rankers.items()}
    # value reached by budget: lets the page compute profit for any save rate and call cost
    out["value_curves"] = {n: value_curve(sc, y_te, v_te) for n, sc in rankers.items()}
    out["wins_across_grid"] = {n: sum(1 for r in out["profit_grid"] if max(rankers, key=lambda m: r[m]["profit"]) == n) for n in rankers}

    mlflow.set_tracking_uri("sqlite:///mlflow.db"); mlflow.set_experiment("p4_rank_calibrate")
    with mlflow.start_run(run_name="p4"):
        mlflow.log_metrics({"ece_raw": out["calibration"]["raw"]["ece"], "ece_em": out["calibration"]["isotonic_plus_em"]["ece"],
                            "estimated_rate": pi_hat, **{f"profit10_{n}": central[n]["profit"] for n in rankers}})
    for n in rankers:
        c = central[n]
        print(f"{n:15} profit@10% {c['profit']:>12,.0f} · churners reached {c['churners_reached']:.3f} · value at risk reached {c['value_at_risk_reached']:.3f}", flush=True)
    print(f"G1 (LambdaMART > probability): {out['gate_G1_passed']} · G2 (ECE ≤ {ECE_GATE}): {out['calibration']['gate_G2_passed']} · "
          f"recommendation: {out['recommendation']} · wins across grid: {out['wins_across_grid']}", flush=True)
    path = Path(cfg["paths"]["outputs_dir"]) / "p4_rank_calibrate.json"
    path.write_text(json.dumps(out, indent=2)); print("wrote", path)


if __name__ == "__main__":
    main()
