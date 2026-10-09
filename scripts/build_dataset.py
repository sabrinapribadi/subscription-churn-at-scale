"""Phase 1 dataset: cohorts × point-in-time features (ADR-001, ADR-002 Am. 1).

Official labels for 2017-02 and 2017-03; reconstructed labels for earlier months.
Writes ~/data/kkbox/features/k{k}_w{W}/cohort=YYYYMM and data/outputs/p1_dataset.json.

    python scripts/build_dataset.py --months 201611 201612 201701 201702 201703
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.cohorts import build_cohort_labels_fast, last_expiry_before, month_bounds  # noqa: E402
from src.features.build import add_snapshot, build_features, build_features_multi  # noqa: E402
from src.spark_session import get_spark  # noqa: E402

OFFICIAL = {201702: "train.csv", 201703: "train_v2.csv"}


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", type=int, required=True)
    ap.add_argument("--k", type=int, default=cfg["framing"]["lead_days"])
    ap.add_argument("--W", type=int, default=cfg["framing"]["window_days"])
    ap.add_argument("--windows", nargs="+", type=int, help="P2: build every window in one pass (writes k{k}_wmulti)")
    a = ap.parse_args()

    raw = Path(cfg["paths"]["raw_dir"]).expanduser()
    pq = Path(cfg["paths"]["parquet_dir"]).expanduser()
    tag = f"k{a.k}_wmulti" if a.windows else f"k{a.k}_w{a.W}"
    out = Path(cfg["paths"]["parquet_dir"]).expanduser().parent / "features" / tag
    spark = get_spark(driver_memory=cfg["spark"]["driver_memory"])
    spark.sparkContext.setLogLevel("ERROR")
    tx = spark.read.parquet(str(pq / "transactions")).cache()
    ul = spark.read.parquet(str(pq / "user_logs"))
    members = spark.read.parquet(str(pq / "members"))

    stats_path = Path(cfg["paths"]["outputs_dir"]) / ("p2_dataset.json" if a.windows else "p1_dataset.json")
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
    for ym in a.months:
        t0 = time.time()
        y, m = divmod(ym, 100)
        if ym in OFFICIAL:
            off = spark.read.csv(str(raw / OFFICIAL[ym]), header=True, inferSchema=True)
            lo, hi = month_bounds(y, m)
            exp = last_expiry_before(tx, y, m)
            joined = off.join(exp, "msno", "left")
            n_off = off.count()
            cohort = joined.filter(F.col("last_expire").between(lo, hi)).select(
                "msno", "last_expire", F.col("is_churn").alias("label"), F.lit("official").alias("label_source"))
        else:
            n_off = None
            cohort = build_cohort_labels_fast(tx, y, m).select(
                "msno", "last_expire", F.col("is_churn").alias("label"), F.lit("reconstructed").alias("label_source"))
        cohort = add_snapshot(cohort.withColumn("cohort", F.lit(ym)), a.k).cache()
        n, churn = cohort.count(), cohort.agg(F.avg("label")).first()[0]
        feats = build_features_multi(tx, ul, members, cohort, a.windows) if a.windows else build_features(tx, ul, members, cohort, a.W)
        feats.write.mode("overwrite").parquet(str(out / f"cohort={ym}"))
        stats[f"{tag}:{ym}"] = {
            "members": n, "churn_rate": round(churn, 5), "label_source": "official" if ym in OFFICIAL else "reconstructed",
            "official_members": n_off, "official_coverage": round(n / n_off, 5) if n_off else None,
            "seconds": round(time.time() - t0),
        }
        print(ym, stats[f"{tag}:{ym}"], flush=True)
        cohort.unpersist()
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, indent=2))
    spark.stop()


if __name__ == "__main__":
    main()
