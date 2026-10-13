"""SparkSession factory: local (pins a Spark-supported JDK) or the Databricks session (ADR-008)."""

from __future__ import annotations

import os
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession

from src.config import ON_DATABRICKS

DEFAULT_JAVA_HOME = "/opt/homebrew/opt/openjdk@17"


def get_spark(app_name: str = "churn-at-scale", driver_memory: str = "8g") -> SparkSession:
    if ON_DATABRICKS:  # serverless: the platform owns the session and its sizing
        return SparkSession.builder.getOrCreate()
    # Override, not setdefault: a shell-wide JAVA_HOME (e.g. JDK 20) would otherwise win,
    # and Spark 4 supports only Java 17/21. CHURN_JAVA_HOME lets other machines choose.
    java_home = os.environ.get("CHURN_JAVA_HOME", DEFAULT_JAVA_HOME)
    if Path(java_home).exists():
        os.environ["JAVA_HOME"] = java_home
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.shuffle.partitions", "64")
        .getOrCreate()
    )


def cache(df: DataFrame) -> DataFrame:
    """Cache locally; serverless Databricks does not support caching, and does not need it."""
    return df if ON_DATABRICKS else df.cache()


def uncache(df: DataFrame) -> None:
    if not ON_DATABRICKS:
        df.unpersist()
