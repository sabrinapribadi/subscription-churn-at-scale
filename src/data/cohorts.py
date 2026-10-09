"""Spark wrapper around the label port: build one expiry cohort's labels at scale (ADR-001)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from src.data.labels import Txn, is_churn, last_expire

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


def build_cohort_labels(transactions: DataFrame, year: int, month: int) -> DataFrame:
    """Labels for members whose last expiry (from the previous month's history) falls in year-month.

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
