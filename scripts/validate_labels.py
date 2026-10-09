"""P0 gate (ADR-001/002): reconstructed labels vs official WSDM labels.

Builds the Feb-2017 and Mar-2017 cohorts from transactions and compares them to
train.csv / train_v2.csv. Writes data/outputs/p0_label_agreement.json.

    python scripts/validate_labels.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.cohorts import build_cohort_labels  # noqa: E402
from src.spark_session import get_spark  # noqa: E402

OFFICIAL = {(2017, 2): "train.csv", (2017, 3): "train_v2.csv"}


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    raw = Path(cfg["paths"]["raw_dir"]).expanduser()
    pq = Path(cfg["paths"]["parquet_dir"]).expanduser()
    gate = cfg["validation"]["gates"]["label_agreement_min"]

    spark = get_spark(driver_memory=cfg["spark"]["driver_memory"])
    txns = spark.read.parquet(str(pq / "transactions")).cache()

    results = {}
    for (year, month), fname in OFFICIAL.items():
        ours = build_cohort_labels(txns, year, month).withColumnRenamed("is_churn", "ours").cache()
        official = spark.read.csv(str(raw / fname), header=True, inferSchema=True).withColumnRenamed("is_churn", "official")

        both = ours.join(official, "msno", "inner")
        n_ours, n_official, n_both = ours.count(), official.count(), both.count()
        agree = both.filter(F.col("ours") == F.col("official")).count()
        confusion = {
            f"ours={r['ours']},official={r['official']}": r["count"]
            for r in both.groupBy("ours", "official").count().collect()
        }
        key = f"{year}-{month:02d}"
        results[key] = {
            "official_members": n_official,
            "reconstructed_members": n_ours,
            "overlap_members": n_both,
            "official_covered_pct": round(100 * n_both / n_official, 3),
            "label_agreement_on_overlap": round(agree / n_both, 5),
            "churn_rate_ours": round(ours.agg(F.avg("ours")).first()[0], 5),
            "churn_rate_official": round(official.agg(F.avg("official")).first()[0], 5),
            "confusion_on_overlap": confusion,
            "gate_min": gate,
            "gate_passed": agree / n_both >= gate,
        }
        print(key, json.dumps(results[key], indent=2))

    out = Path(cfg["paths"]["outputs_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "p0_label_agreement.json").write_text(json.dumps(results, indent=2))
    spark.stop()


if __name__ == "__main__":
    main()
