"""Spark wrapper around the label port: build one expiry cohort's labels at scale (ADR-001)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from src.data.labels import CHURN_GAP_DAYS, Txn, is_churn, last_expire

TXN_COLS = [
    "payment_method_id",
    "payment_plan_days",
    "plan_list_price",
    "transaction_date",
    "membership_expire_date",
    "is_cancel",
]


def month_bounds(year: int, month: int) -> tuple[int, int]:
    """First and last day of a month as yyyymmdd ints."""
    first = date(year, month, 1)
    nxt = date(year + month // 12, month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return int(first.strftime("%Y%m%d")), int(last.strftime("%Y%m%d"))


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _rows(pdf: pd.DataFrame) -> list[Txn]:
    return [Txn(*map(int, r)) for r in pdf[TXN_COLS].itertuples(index=False)]


def _with_order_key(df: DataFrame) -> DataFrame:
    """Columns that make the official comparator a plain sort (see src/data/labels.py:_lt).

    Ascending order = transaction_date ↑, signature ↓ (string), is_cancel ↑, then expiry ↑ for
    renewals and ↓ for cancels. Rows tied on all four keys are identical for labelling purposes.
    """
    sig = F.concat(
        F.col("plan_list_price").cast("string"),
        F.col("payment_plan_days").cast("string"),
        F.col("payment_method_id").cast("string"),
    )
    k_expire = F.when(F.col("is_cancel") == 0, F.col("membership_expire_date")).otherwise(-F.col("membership_expire_date"))
    return df.withColumn("_sig", sig).withColumn("_kexp", k_expire)


def _to_date(col: str):
    return F.to_date(F.col(col).cast("string"), "yyyyMMdd")


def build_cohort_labels_fast(
    transactions: DataFrame, year: int, month: int, full_history: bool = False
) -> DataFrame:
    """Spark-native equivalent of build_cohort_labels — window functions instead of per-member Python.

    Same output columns. Equality with the reference implementation is enforced by
    tests/test_cohorts_spark.py on randomly generated transaction histories.
    """
    h_start, h_end = month_bounds(*previous_month(year, month))
    if full_history:
        h_start = 0  # every transaction before the target month (ADR-001 Amendment 2 hypothesis)
    c_start, c_end = month_bounds(year, month)
    txns = _with_order_key(transactions)

    last_first = Window.partitionBy("msno").orderBy(
        F.col("transaction_date").desc(), F.col("_sig").asc(), F.col("is_cancel").desc(), F.col("_kexp").desc()
    )
    candidates = (
        txns.filter(F.col("transaction_date").between(h_start, h_end))
        .withColumn("_rn", F.row_number().over(last_first))
        .filter(F.col("_rn") == 1)
        .select("msno", F.col("membership_expire_date").alias("last_expire"))
        .filter(F.col("last_expire").between(c_start, c_end))
    )

    in_order = Window.partitionBy("msno").orderBy(
        F.col("transaction_date").asc(), F.col("_sig").desc(), F.col("is_cancel").asc(), F.col("_kexp").asc()
    )
    future = (
        txns.filter(F.col("transaction_date") > h_end)
        .join(candidates.select("msno"), "msno", "inner")
        .withColumn("_rn", F.row_number().over(in_order))
    )
    first_renewal = future.filter(F.col("is_cancel") == 0).groupBy("msno").agg(F.min("_rn").alias("_r_star"))
    per_member = (
        future.join(first_renewal, "msno", "left")
        .groupBy("msno")
        .agg(
            F.first("_r_star", ignorenulls=True).alias("_r_star"),
            F.min(F.when(F.col("_rn") == F.col("_r_star"), F.col("transaction_date"))).alias("_renew_date"),
            F.min(
                F.when((F.col("is_cancel") == 1) & (F.col("_r_star").isNull() | (F.col("_rn") < F.col("_r_star"))),
                       F.col("membership_expire_date"))
            ).alias("_cancel_expire"),
        )
    )
    out = candidates.join(per_member, "msno", "left").withColumn(
        "_eff_expire", F.least(F.col("last_expire"), F.col("_cancel_expire"))
    )
    gap = F.datediff(_to_date("_renew_date"), _to_date("_eff_expire"))
    churn = F.when(F.col("_r_star").isNull(), 1).when(gap >= CHURN_GAP_DAYS, 1).otherwise(0)
    return out.select("msno", "last_expire", churn.cast("int").alias("is_churn"))


def build_cohort_labels(transactions: DataFrame, year: int, month: int) -> DataFrame:
    """Reference implementation (per-member Python, slow). Kept as the oracle for tests.

    Labels for members whose last expiry (from the previous month's history) falls in year-month.

    Mirrors the official labeller: history = previous calendar month only; future = every
    transaction after the history window. Returns msno, last_expire, is_churn.
    """
    h_start, h_end = month_bounds(*previous_month(year, month))
    c_start, c_end = month_bounds(year, month)

    history = transactions.filter(F.col("transaction_date").between(h_start, h_end))
    future = transactions.filter(F.col("transaction_date") > h_end)

    def _last_expire(pdf: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"msno": [pdf["msno"].iat[0]], "last_expire": [last_expire(_rows(pdf))]})

    candidates = (
        history.groupBy("msno")
        .applyInPandas(_last_expire, schema="msno string, last_expire int")
        .filter(F.col("last_expire").between(c_start, c_end))
    )

    joined = candidates.join(future, on="msno", how="left")

    def _label(pdf: pd.DataFrame) -> pd.DataFrame:
        expire = int(pdf["last_expire"].iat[0])
        fut = pdf.dropna(subset=["payment_method_id"])
        return pd.DataFrame(
            {"msno": [pdf["msno"].iat[0]], "last_expire": [expire], "is_churn": [int(is_churn(_rows(fut), expire))]}
        )

    return joined.groupBy("msno").applyInPandas(
        _label, schema="msno string, last_expire int, is_churn int"
    )
