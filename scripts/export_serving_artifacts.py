"""Export the P4 model (k = 14, W = 30, train Feb-2017) and the scored Mar-2017 cohort for the services (ADR-005).

    python scripts/export_serving_artifacts.py            # → ~/data/kkbox/serving
"""

from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.dataset as ds
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.baseline import canonical_rows, feature_columns, prepare  # noqa: E402
from src.models.ranking import member_value  # noqa: E402
from src.services.artifacts import build_artifacts  # noqa: E402

TRAIN, TEST, K = 201702, 201703, 14


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    store = Path(cfg["paths"]["parquet_dir"]).expanduser().parent
    W = cfg["framing"]["window_days_selected"]
    # same build as the Databricks job (scripts/build_dataset.py --W 30), features in a fixed order (ADR-008)
    data = canonical_rows(prepare(ds.dataset(Path(cfg["paths"]["features_dir"]).expanduser() / f"k{K}_w{W}", format="parquet",
                                             partitioning=None).to_table().to_pandas()))
    feats = feature_columns(data)
    data["member_value"] = member_value(data, cfg["business"]["value_horizon_days"])
    train = data[data["cohort"] == TRAIN].reset_index(drop=True)
    test = data[data["cohort"] == TEST].reset_index(drop=True)
    p4 = json.loads(Path(cfg["paths"]["outputs_dir"], "p4_rank_calibrate.json").read_text())
    scenarios = {"members": p4["setup"]["test_members"], "value_curves": p4["value_curves"], "source": "data/outputs/p4_rank_calibrate.json"}
    info = build_artifacts(train, test, feats, store / "serving", scenarios=scenarios, tag=f"lgbm-k{K}w{W}")
    labels = test[["msno", "label", "member_value"]].copy()
    labels.to_parquet(store / "serving_eval_labels.parquet", index=False)  # kept outside serving/: services never see labels
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
