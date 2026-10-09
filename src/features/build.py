"""Point-in-time features for one cohort snapshot (ADR-001).

Every feature for member m uses only rows dated strictly before the member's snapshot
date S = E − k. Transactions use the full history before S; listening logs use the
window [S − W, S). tests/test_features.py fails if any row on or after S changes a feature.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

SECONDS_PER_DAY = 86_400
RECENT_DAYS = 14

CATEGORICAL = ["city", "gender", "registered_via", "last_payment_method"]


def _d(col: str):
    return F.to_date(F.col(col).cast("string"), "yyyyMMdd")


def _int_date(expr):
    return F.date_format(expr, "yyyyMMdd").cast("int")


def add_snapshot(cohort: DataFrame, lead_days: int) -> DataFrame:
    """cohort(msno, last_expire, ...) → adds snapshot (int yyyymmdd) = last_expire − k days."""
    return cohort.withColumn("snapshot", _int_date(F.date_sub(_d("last_expire"), lead_days)))


def transaction_features(tx: DataFrame, cohort: DataFrame, window_days: int) -> DataFrame:
    s = cohort.select("msno", "snapshot")
    t = tx.join(s, "msno").filter(F.col("transaction_date") < F.col("snapshot"))
    w_start = _int_date(F.date_sub(_d("snapshot"), window_days))
    last = F.struct("transaction_date", "membership_expire_date")
    return t.groupBy("msno").agg(
        F.count("*").alias("tx_count"),
        F.sum((F.col("transaction_date") >= w_start).cast("int")).alias("tx_count_window"),
        F.sum("is_cancel").alias("tx_cancels"),
        F.sum(((F.col("transaction_date") >= w_start) & (F.col("is_cancel") == 1)).cast("int")).alias("tx_cancels_window"),
        F.avg("is_auto_renew").alias("tx_auto_renew_share"),
        F.avg(F.col("plan_list_price") - F.col("actual_amount_paid")).alias("tx_mean_discount"),
        F.countDistinct("payment_method_id").alias("tx_distinct_methods"),
        F.min("transaction_date").alias("_first_tx"),
        F.max("transaction_date").alias("_last_tx"),
        F.max_by("payment_plan_days", last).alias("last_plan_days"),
        F.max_by("plan_list_price", last).alias("last_list_price"),
        F.max_by("actual_amount_paid", last).alias("last_amount_paid"),
        F.max_by("is_auto_renew", last).alias("last_auto_renew"),
        F.max_by("payment_method_id", last).alias("last_payment_method"),
        F.max_by("is_cancel", last).alias("last_is_cancel"),
        F.first("snapshot").alias("_snap"),
    ).select(
        "*",
        F.datediff(_d("_snap"), _d("_first_tx")).alias("tenure_days"),
        F.datediff(_d("_snap"), _d("_last_tx")).alias("days_since_last_tx"),
    ).drop("_first_tx", "_last_tx", "_snap")


def usage_features(user_logs: DataFrame, cohort: DataFrame, window_days: int) -> DataFrame:
    s = cohort.select("msno", "snapshot").withColumn("w_start", _int_date(F.date_sub(_d("snapshot"), window_days)))
    s = s.withColumn("r_start", _int_date(F.date_sub(_d("snapshot"), RECENT_DAYS)))
    lo = s.agg(F.min("w_start")).first()[0]
    hi = s.agg(F.max("snapshot")).first()[0]
    ul = (
        user_logs.filter(F.col("year_month").between(lo // 100, hi // 100))
        .filter(F.col("date").between(lo, hi))
        .join(s, "msno")
        .filter((F.col("date") >= F.col("w_start")) & (F.col("date") < F.col("snapshot")))
        .withColumn("secs", F.least(F.greatest(F.col("total_secs"), F.lit(0.0)), F.lit(float(SECONDS_PER_DAY))))
        .withColumn("plays", F.col("num_25") + F.col("num_50") + F.col("num_75") + F.col("num_985") + F.col("num_100"))
        .withColumn("recent", (F.col("date") >= F.col("r_start")).cast("int"))
    )
    return ul.groupBy("msno").agg(
        F.count("*").alias("use_active_days"),
        F.sum("recent").alias("use_active_days_recent"),
        F.sum("secs").alias("use_secs"),
        F.sum(F.col("secs") * F.col("recent")).alias("_secs_recent"),
        F.avg("num_unq").alias("use_unique_songs_mean"),
        F.sum("plays").alias("_plays"),
        F.sum("num_100").alias("_full"),
        F.sum("num_25").alias("_skipped"),
        F.max("date").alias("_last_play"),
        F.first("snapshot").alias("_snap"),
    ).select(
        "msno", "use_active_days", "use_active_days_recent", "use_secs", "use_unique_songs_mean",
        (F.col("use_secs") / window_days).alias("use_secs_per_day"),
        (F.col("_secs_recent") / RECENT_DAYS).alias("use_secs_per_day_recent"),
        ((F.col("_secs_recent") / RECENT_DAYS) / (F.col("use_secs") / window_days + 1e-9)).alias("use_decline_ratio"),
        (F.col("_full") / (F.col("_plays") + 1e-9)).alias("use_full_listen_share"),
        (F.col("_skipped") / (F.col("_plays") + 1e-9)).alias("use_skip_share"),
        F.datediff(_d("_snap"), _d("_last_play")).alias("days_since_last_play"),
    )


def member_features(members: DataFrame, cohort: DataFrame) -> DataFrame:
    m = members.join(cohort.select("msno", "snapshot"), "msno")
    return m.select(
        "msno",
        "city",
        F.when(F.col("gender") == "male", 1).when(F.col("gender") == "female", 2).otherwise(0).alias("gender"),
        "registered_via",
        F.when(F.col("bd").between(10, 80), F.col("bd")).alias("age"),
        F.datediff(_d("snapshot"), _d("registration_init_time")).alias("registration_days"),
    )


def build_features(tx: DataFrame, user_logs: DataFrame, members: DataFrame, cohort: DataFrame, window_days: int) -> DataFrame:
    """cohort must carry msno, cohort, last_expire, snapshot, label, label_source."""
    base = cohort.select("msno", "cohort", "last_expire", "snapshot", "label", "label_source")
    return (
        base.join(transaction_features(tx, cohort, window_days), "msno", "left")
        .join(usage_features(user_logs, cohort, window_days), "msno", "left")
        .join(member_features(members, cohort), "msno", "left")
        .fillna(0, subset=["use_active_days", "use_active_days_recent", "use_secs", "use_secs_per_day", "use_secs_per_day_recent"])
    )
