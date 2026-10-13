"""Config loader: the default config, plus an overlay for other environments (ADR-008).

On Databricks the overlay configs/databricks.yaml is applied automatically (Unity Catalog volume
paths); CHURN_CONFIG=<path> picks any other overlay.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ON_DATABRICKS = "DATABRICKS_RUNTIME_VERSION" in os.environ


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(overlay: str | None = None) -> dict:
    cfg = yaml.safe_load((ROOT / "configs" / "default_config.yaml").read_text())
    path = overlay or os.environ.get("CHURN_CONFIG") or ("configs/databricks.yaml" if ON_DATABRICKS else None)
    if path:
        p = Path(path) if Path(path).is_absolute() else ROOT / path
        cfg = _merge(cfg, yaml.safe_load(p.read_text()))
    return cfg
