"""P3 input: daily listening sequences before each member's snapshot (ADR-003).

For every member in the k-day feature set, writes the D days before the snapshot as
long-format rows (msno, pos, 7 channels), pos 0 = oldest day, D-1 = the day before the
snapshot. Inactive days are simply absent (filled with zeros when arrays are built).

    python scripts/build_sequences.py --k 14 --days 60 --months 201702 201703
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.spark_session import get_spark  # noqa: E402

CHANNELS = ["num_25", "num_50", "num_75", "num_985", "num_100", "num_unq", "minutes"]


def _d(col: str):
    return F.to_date(F.col(col).cast("string"), "yyyyMMdd")


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=14)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--months", nargs="+", type=int, required=True)
    a = ap.parse_args()
    store = Path(cfg["paths"]["parquet_dir"]).expanduser().parent
    spark = get_spark(driver_memory=cfg["spark"]["driver_memory"])
    spark.sparkContext.setLogLevel("ERROR")
    ul = spark.read.parquet(str(store / "parquet" / "user_logs"))
    for ym in a.months:
        t0 = time.time()
        snap = spark.read.parquet(str(store / "features" / f"k{a.k}_wmulti" / f"cohort={ym}")).select("msno", "snapshot")
        snap = snap.withColumn("start", F.date_format(F.date_sub(_d("snapshot"), a.days), "yyyyMMdd").cast("int"))
        lo, hi = snap.agg(F.min("start"), F.max("snapshot")).first()
        rows = (
            ul.filter(F.col("year_month").between(lo // 100, hi // 100)).filter(F.col("date").between(lo, hi))
            .join(snap, "msno")
            .filter((F.col("date") >= F.col("start")) & (F.col("date") < F.col("snapshot")))
            .withColumn("pos", F.lit(a.days) - F.datediff(_d("snapshot"), _d("date")))
            .select(
                "msno", F.col("pos").cast("short").alias("pos"),
                *[F.log1p(F.greatest(F.col(c), F.lit(0))).cast("float").alias(c) for c in CHANNELS[:6]],
                F.log1p(F.least(F.greatest(F.col("total_secs"), F.lit(0.0)), F.lit(86400.0)) / 60).cast("float").alias("minutes"),
            )
        )
        out = store / "sequences" / f"k{a.k}_d{a.days}" / f"cohort={ym}"
        rows.write.mode("overwrite").parquet(str(out))
        n = spark.read.parquet(str(out)).count()
        print(f"{ym}: {n:,} member-days in {time.time() - t0:.0f}s -> {out}", flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
