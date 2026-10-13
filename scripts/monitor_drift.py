"""P7 monitoring (ADR-009): drift per feature and for the score, plus the lagged realised-vs-expected check.

    python scripts/monitor_drift.py            # locally: serving model in ~/data/kkbox/serving
                                               # on Databricks: job task after train_register

Reference = the training cohort (Feb 2017), current = the scored cohort (Mar 2017). Writes
p7_drift.json (and drift_psi.parquet on Databricks, published as a table by task 4).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.dataset as ds


def _repo_root() -> Path:  # Databricks runs job scripts through exec(), without __file__
    for c in (globals().get("__file__"), sys.argv[0] if sys.argv else None, os.path.join(os.getcwd(), "_")):
        if c and (Path(c).resolve().parents[1] / "src" / "config.py").exists():
            return Path(c).resolve().parents[1]
    raise RuntimeError("repo root not found")


sys.path.insert(0, str(_repo_root()))
from src.config import ON_DATABRICKS, load_config  # noqa: E402
from src.models.baseline import canonical_rows, feature_columns, prepare  # noqa: E402
from src.models.ranking import member_value  # noqa: E402
from src.monitoring.drift import ALERT, band, psi, psi_table  # noqa: E402
from src.services.store import apply_calibration  # noqa: E402

TRAIN, TEST, K = 201702, 201703, 14


def main() -> None:
    cfg = load_config()
    P, frac, W = cfg["paths"], cfg["validation"]["top_k_fraction"], cfg["framing"]["window_days_selected"]
    data = canonical_rows(prepare(ds.dataset(Path(P["features_dir"]).expanduser() / f"k{K}_w{W}", format="parquet",
                                             partitioning=None).to_table().to_pandas()))
    feats = feature_columns(data)
    ref, cur = data[data["cohort"] == TRAIN].reset_index(drop=True), data[data["cohort"] == TEST].reset_index(drop=True)

    serving = Path(P["serving_dir"]).expanduser()
    cal = json.loads((serving / "calibration.json").read_text())
    booster = lgb.Booster(model_file=str(serving / "model.txt"))
    assert set(cal["features"]) == set(feats), "model and features disagree"
    raw_r, raw_c = booster.predict(ref[cal["features"]]), booster.predict(cur[cal["features"]])
    p_r, p_c = apply_calibration(raw_r, cal), apply_calibration(raw_c, cal)

    table = psi_table(ref, cur, feats)
    score_psi = psi(pd.Series(p_r), pd.Series(p_c))
    table = pd.concat([pd.DataFrame([{"feature": "score (calibrated)", "psi": round(score_psi, 4), "band": band(score_psi),
                                      "reference_mean": float(p_r.mean()), "current_mean": float(p_c.mean()),
                                      "reference_missing": 0.0, "current_missing": 0.0}]), table], ignore_index=True)

    # lagged check: what the list promised vs what March delivered (labels mature ~30 days after expiry)
    v = member_value(cur, cfg["business"]["value_horizon_days"])
    order = np.lexsort((-raw_c, -(p_c * v)))
    top = order[: int(len(cur) * frac)]
    y = cur["label"].to_numpy()
    lagged = {"list_size": int(len(top)), "expected_churners_on_list": round(float(p_c[top].sum()), 1),
              "realised_churners_on_list": int(y[top].sum()), "expected_churn_rate": round(float(p_c.mean()), 5),
              "realised_churn_rate": round(float(y.mean()), 5), "training_churn_rate": round(float(ref["label"].mean()), 5)}
    lagged["shortfall_on_list"] = round(1 - lagged["expected_churners_on_list"] / lagged["realised_churners_on_list"], 4)

    feature_rows = table[table["feature"] != "score (calibrated)"]
    report = {"reference_cohort": TRAIN, "current_cohort": TEST, "model_version": cal.get("model_version"),
              "features_checked": int(len(feature_rows)), "model_features": len(feats),
              "bands": table["band"].value_counts().to_dict(), "alert_threshold": ALERT,
              "alerts": table.loc[table["band"] == "alert", "feature"].tolist(),
              "watch": table.loc[table["band"] == "watch", "feature"].tolist(),
              "score_psi": round(score_psi, 4), "lagged": lagged, "table": table.round(5).to_dict(orient="records")}
    report["checks"] = {"G2_psi_for_every_feature_and_score": report["features_checked"] == len(feats) and not np.isnan(score_psi),
                        "G3_lagged_check_reported": lagged["realised_churners_on_list"] > 0}
    out = Path(P["outputs_dir"]); out.mkdir(parents=True, exist_ok=True)
    (out / "p7_drift.json").write_text(json.dumps(report, indent=2))
    if ON_DATABRICKS:
        table.assign(reference_cohort=TRAIN, current_cohort=TEST).to_parquet(out / "drift_psi.parquet", index=False)
    print(json.dumps({k: v for k, v in report.items() if k != "table"}, indent=2))
    print(table[["feature", "psi", "band"]].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
