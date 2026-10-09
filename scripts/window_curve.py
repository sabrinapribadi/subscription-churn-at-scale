"""Phase 2: how early can we call (lead time k) and how much history do we need (window W)?

For every k with a k{k}_wmulti feature set, train on Feb-2017 (official) and test on
Mar-2017 (official) once per window W — same model and split as P1 E1. Reports PR-AUC and
churners reached at 5% / 10% of members called, plus the knee per k (ADR-001 grid).

    python scripts/window_curve.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import mlflow
import pyarrow.dataset as ds
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluation.metrics import evaluate, top_k_metrics  # noqa: E402
from src.features.build import select_window  # noqa: E402
from src.models.baseline import NON_FEATURES, fit, prepare  # noqa: E402

TRAIN, TEST = 201702, 201703
KNEE_SHARE = 0.95  # knee = shortest window with >= 95% of the best gain over the shortest window


def knee(windows: list[int], scores: list[float]) -> int:
    gain = max(scores) - scores[0]
    if gain <= 0:
        return windows[0]
    return next(w for w, s in zip(windows, scores) if s - scores[0] >= KNEE_SHARE * gain)


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    frac = cfg["validation"]["top_k_fraction"]
    windows = cfg["framing"]["window_days_grid"]
    root = Path(cfg["paths"]["parquet_dir"]).expanduser().parent / "features"
    leads = sorted(int(p.name[1:].split("_")[0]) for p in root.glob("k*_wmulti"))
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("p2_window_curve")

    results = {"setup": {"train_cohort": TRAIN, "test_cohort": TEST, "windows": windows, "leads": leads,
                         "top_k_fraction": frac, "knee_share": KNEE_SHARE}, "grid": []}
    for k in leads:
        raw = ds.dataset(root / f"k{k}_wmulti", format="parquet", partitioning=None).to_table().to_pandas()
        for W in windows:
            t0 = time.time()
            mapping = select_window(list(raw.columns), W)
            data = prepare(raw[list(mapping)].rename(columns=mapping))
            features = [c for c in data.columns if c not in NON_FEATURES]
            train, test = data[data["cohort"] == TRAIN], data[data["cohort"] == TEST]
            model = fit(train, features)
            p = model.predict_proba(test[features])[:, 1]
            y = test["label"].to_numpy()
            res = evaluate(y, p, frac)
            res["recall_at_5pct"] = top_k_metrics(y, p, 0.05)["recall_at_k"]
            res |= {"lead_days": k, "window_days": W, "test_members": int(len(test)), "best_iteration": int(model.best_iteration_)}
            results["grid"].append(res)
            with mlflow.start_run(run_name=f"k{k}_w{W}"):
                mlflow.log_params({"lead_days": k, "window_days": W, "train_cohort": TRAIN, "test_cohort": TEST})
                mlflow.log_metrics({m: v for m, v in res.items() if isinstance(v, float)})
            print(f"k={k:>2} W={W:>3}  PR-AUC={res['pr_auc']:.4f}  reach@10%={res['recall_at_k']:.3f}  "
                  f"reach@5%={res['recall_at_5pct']:.3f}  n={len(test):,}  {time.time() - t0:.0f}s", flush=True)

    results["knee"] = {}
    for k in leads:
        rows = [r for r in results["grid"] if r["lead_days"] == k]
        scores = [r["pr_auc"] for r in rows]
        best = max(rows, key=lambda r: r["pr_auc"])
        results["knee"][str(k)] = {"knee_window": knee(windows, scores), "best_window": best["window_days"],
                                   "best_pr_auc": best["pr_auc"], "gain_over_shortest": max(scores) - scores[0]}
    out = Path(cfg["paths"]["outputs_dir"]) / "p2_window_curve.json"
    out.write_text(json.dumps(results, indent=2))
    print(json.dumps(results["knee"], indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
