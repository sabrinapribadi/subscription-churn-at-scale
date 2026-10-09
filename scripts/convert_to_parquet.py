"""One-time conversion of the raw KKBox CSVs to typed Parquet (PRD §7).

user_logs (~400M rows) is partitioned by year_month so cohort builds read only the
months they need. Run after extracting the .7z archives into paths.raw_dir.

    python scripts/convert_to_parquet.py [--tables members transactions user_logs]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, LongType, DoubleType, StringType, StructField, StructType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.spark_session import get_spark  # noqa: E402

SCHEMAS = {
    "members": StructType([
        StructField("msno", StringType()),
        StructField("city", IntegerType()),
        StructField("bd", IntegerType()),
        StructField("gender", StringType()),
        StructField("registered_via", IntegerType()),
        StructField("registration_init_time", IntegerType()),
    ]),
    "transactions": StructType([
        StructField("msno", StringType()),
        StructField("payment_method_id", IntegerType()),
        StructField("payment_plan_days", IntegerType()),
        StructField("plan_list_price", IntegerType()),
        StructField("actual_amount_paid", IntegerType()),
        StructField("is_auto_renew", IntegerType()),
        StructField("transaction_date", IntegerType()),
        StructField("membership_expire_date", IntegerType()),
        StructField("is_cancel", IntegerType()),
    ]),
    "user_logs": StructType([
        StructField("msno", StringType()),
        StructField("date", IntegerType()),
        StructField("num_25", IntegerType()),
        StructField("num_50", IntegerType()),
        StructField("num_75", IntegerType()),
        StructField("num_985", IntegerType()),
        StructField("num_100", IntegerType()),
        StructField("num_unq", IntegerType()),
        StructField("total_secs", DoubleType()),
    ]),
}

# v1 + v2 files are unioned; v2 extends the timeline to March 2017.
SOURCES = {
    "members": ["members_v3.csv"],
    "transactions": ["transactions.csv", "transactions_v2.csv"],
    "user_logs": ["user_logs.csv", "user_logs_v2.csv"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", nargs="+", default=list(SOURCES))
    parser.add_argument("--config", default="configs/default_config.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    raw = Path(cfg["paths"]["raw_dir"]).expanduser()
    out = Path(cfg["paths"]["parquet_dir"]).expanduser()
    spark = get_spark(driver_memory=cfg["spark"]["driver_memory"])

    for table in args.tables:
        files = [str(raw / f) for f in SOURCES[table] if (raw / f).exists()]
        if not files:
            print(f"[skip] {table}: no CSV found in {raw}")
            continue
        df = spark.read.csv(files, header=True, schema=SCHEMAS[table])
        if table == "user_logs":
            # No dropDuplicates here: a full shuffle of ~400M rows is the most expensive step
            # and v1/v2 cover disjoint months. Duplicates are checked in validate_data.py.
            df = df.withColumn("year_month", (F.col("date") / 100).cast(LongType()))
            writer = (
                df.repartition("year_month")
                .write.mode("overwrite")
                .option("maxRecordsPerFile", 5_000_000)
                .partitionBy("year_month")
            )
        else:
            writer = df.dropDuplicates().write.mode("overwrite")
        writer.parquet(str(out / table))
        print(f"[done] {table}: {files} -> {out / table}")

    spark.stop()


if __name__ == "__main__":
    main()
