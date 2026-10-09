"""Local SparkSession factory. Pins a Spark-supported JDK without touching the system default."""

from __future__ import annotations

import os
from pathlib import Path

from pyspark.sql import SparkSession

DEFAULT_JAVA_HOME = "/opt/homebrew/opt/openjdk@17"


def get_spark(app_name: str = "churn-at-scale", driver_memory: str = "8g") -> SparkSession:
    if Path(DEFAULT_JAVA_HOME).exists():
        os.environ.setdefault("JAVA_HOME", DEFAULT_JAVA_HOME)
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.shuffle.partitions", "64")
        .getOrCreate()
    )
