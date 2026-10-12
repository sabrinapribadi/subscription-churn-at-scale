"""Build the versioned serving artefacts the services load (ADR-005). Used by the export script and by tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.models.baseline import fit, holdout_split
from src.models.ranking import fit_isotonic, prior_shift_em

KEYS = ["msno", "cohort", "snapshot", "last_expire"]


def build_artifacts(train: pd.DataFrame, score_on: pd.DataFrame, features: list[str], out_dir: str | Path,
                    scenarios: dict | None = None, tag: str = "lgbm") -> dict:
    """Train on `train`, calibrate on its hold-out, re-estimate the churn rate on unlabelled `score_on`, write artefacts."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    model = fit(train, features)
    tr_idx, va_idx = holdout_split(train)
    iso = fit_isotonic(model.predict_proba(train.iloc[va_idx][features])[:, 1], train["label"].to_numpy()[va_idx])
    prior_train = float(train["label"].to_numpy()[tr_idx].mean())
    p_iso = iso.predict(model.predict_proba(score_on[features])[:, 1])
    _, prior_new = prior_shift_em(p_iso, prior_train)  # no labels from score_on are used
    model.booster_.save_model(str(out / "model.txt"))
    digest = hashlib.sha256((out / "model.txt").read_bytes()).hexdigest()[:8]
    cal = {"model_version": f"{tag}-{digest}", "features": features, "iso_x": [float(x) for x in iso.X_thresholds_],
           "iso_y": [float(y) for y in iso.y_thresholds_], "prior_train": prior_train, "prior_new": float(prior_new)}
    (out / "calibration.json").write_text(json.dumps(cal))
    cols = KEYS + features + ["member_value"]
    score_on[cols].to_parquet(out / "features.parquet", index=False)
    if scenarios:
        (out / "scenarios.json").write_text(json.dumps(scenarios))
    return {"model_version": cal["model_version"], "members": int(len(score_on)), "prior_train": prior_train, "prior_new": float(prior_new)}
