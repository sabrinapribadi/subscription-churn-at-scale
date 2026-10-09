"""Phase 1 baseline: LightGBM on point-in-time features, tested out-of-time (ADR-002 Am. 1).

Experiments (all tested on the 2017-03 cohort with official labels):
  E1 benchmark  — train 2017-02 (official). Comparable to published work, but Feb labels
                  are not yet known at March snapshot time.
  E2 realistic  — train 2016-11..2017-01 (reconstructed). Only labels that exist at prediction time.
  E3 combined   — train 2016-11..2017-02.
Plus a rule baseline (manual renewal first, then least recent listening) that every model must beat.

    python scripts/train_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluation.metrics import evaluate  # noqa: E402
from src.models.baseline import NON_FEATURES, PARAMS, fit, prepare  # noqa: E402

TEST = 201703
EXPERIMENTS = {
    "E1_benchmark": [201702],
    "E2_realistic": [201611, 201612, 201701],
    "E3_combined": [201611, 201612, 201701, 201702],
}


def rule_score(df: pd.DataFrame) -> np.ndarray:
    # Manual-renewal members first; within each group, longer since last play = riskier.
    manual = 1 - df["last_auto_renew"].fillna(0).to_numpy()
    idle = df["days_since_last_play"].fillna(999).clip(0, 999).to_numpy() / 1000
    return manual + idle


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    k, W, frac = cfg["framing"]["lead_days"], cfg["framing"]["window_days"], cfg["validation"]["top_k_fraction"]
    root = Path(cfg["paths"]["parquet_dir"]).expanduser().parent / "features" / f"k{k}_w{W}"
    # Files carry their own `cohort` column; ignore the folder-name partition to avoid a type clash.
    data = ds.dataset(root, format="parquet", partitioning=None).to_table().to_pandas()
    data = prepare(data)
    features = [c for c in data.columns if c not in NON_FEATURES]

    test = data[data["cohort"] == TEST]
    y_test = test["label"].to_numpy()
    results = {"setup": {"lead_days": k, "window_days": W, "test_cohort": TEST, "top_k_fraction": frac,
                         "features": features}}
    results["rule_baseline"] = evaluate(y_test, rule_score(test), frac)
    store = Path(cfg["paths"]["parquet_dir"]).expanduser().parent
    (store / "models").mkdir(parents=True, exist_ok=True)
    preds = test[["msno", "label", "last_auto_renew", "tenure_days", "last_plan_days", "last_list_price"]].copy()
    preds["score_rule"] = rule_score(test)
    print("rule baseline", json.dumps(results["rule_baseline"]))

    mlflow.set_tracking_uri(cfg.get("mlflow_uri", "sqlite:///mlflow.db"))
    mlflow.set_experiment("p1_baseline")
    for name, cohorts in EXPERIMENTS.items():
        train = data[data["cohort"].isin(cohorts)]
        model = fit(train, features)
        p = model.predict_proba(test[features])[:, 1]
        res = evaluate(y_test, p, frac) | {
            "train_cohorts": cohorts, "train_rows": int(len(train)), "train_churn_rate": float(train["label"].mean()),
            "best_iteration": int(model.best_iteration_),
        }
        gain = pd.Series(model.booster_.feature_importance("gain"), index=features)
        res["top_features"] = (gain / gain.sum()).sort_values(ascending=False).head(12).round(4).to_dict()
        results[name] = res
        preds[f"score_{name}"] = p
        model.booster_.save_model(str(store / "models" / f"p1_{name}.txt"))
        with mlflow.start_run(run_name=name):
            mlflow.log_params({**{k_: v for k_, v in PARAMS.items()}, "train_cohorts": ",".join(map(str, cohorts)),
                               "test_cohort": TEST, "lead_days": k, "window_days": W})
            mlflow.log_metrics({m: v for m, v in res.items() if isinstance(v, float)})
            mlflow.log_dict(res["top_features"], "top_features.json")
        print(name, json.dumps({m: round(v, 4) for m, v in res.items() if isinstance(v, float)}), flush=True)

    (store / "predictions").mkdir(parents=True, exist_ok=True)
    preds.to_parquet(store / "predictions" / f"p1_test_{TEST}.parquet", index=False)
    out = Path(cfg["paths"]["outputs_dir"]) / "p1_baseline.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
