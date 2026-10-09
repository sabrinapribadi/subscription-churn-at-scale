"""Spark smoke test: the cohort builder reproduces the pure-Python label rules end to end."""

import random
from datetime import date, timedelta

import pytest

pyspark = pytest.importorskip("pyspark")

from src.data.cohorts import build_cohort_labels, build_cohort_labels_fast, month_bounds  # noqa: E402
from src.spark_session import get_spark  # noqa: E402

COLS = [
    "msno", "payment_method_id", "payment_plan_days", "plan_list_price", "actual_amount_paid",
    "is_auto_renew", "transaction_date", "membership_expire_date", "is_cancel",
]


@pytest.fixture(scope="module")
def spark():
    s = get_spark("test", driver_memory="1g")
    yield s
    s.stop()


def test_month_bounds_handles_february_and_december():
    assert month_bounds(2017, 2) == (20170201, 20170228)
    assert month_bounds(2016, 12) == (20161201, 20161231)


def test_february_cohort(spark):
    rows = [
        # renews 14 days after expiry -> not churn
        ("a", 41, 30, 149, 149, 0, 20170115, 20170215, 0),
        ("a", 41, 30, 149, 149, 0, 20170301, 20170401, 0),
        # no future activity -> churn
        ("b", 41, 30, 149, 149, 0, 20170110, 20170210, 0),
        # expiry outside February -> not a candidate
        ("c", 41, 30, 149, 149, 0, 20170105, 20170305, 0),
        # renews 35 days late -> churn
        ("d", 41, 30, 149, 149, 0, 20170120, 20170220, 0),
        ("d", 41, 30, 149, 149, 0, 20170327, 20170427, 0),
        # no January history -> not a candidate
        ("e", 41, 30, 149, 149, 0, 20161215, 20170215, 0),
    ]
    df = spark.createDataFrame(rows, COLS)
    out = {r.msno: r.is_churn for r in build_cohort_labels(df, 2017, 2).collect()}
    assert out == {"a": 0, "b": 1, "d": 1}
    fast = {r.msno: r.is_churn for r in build_cohort_labels_fast(df, 2017, 2).collect()}
    assert fast == out


def test_fast_matches_reference_on_random_histories(spark):
    """Property test: 400 random members with same-day plans, cancels and renewals."""
    rng = random.Random(42)
    rows = []
    for m in range(400):
        for _ in range(rng.randint(1, 6)):
            day = rng.choice([20170105, 20170115, 20170115, 20170131, 20170201, 20170210, 20170228, 20170305, 20170320])
            plan_days = rng.choice([30, 30, 90, 7])
            price = rng.choice([99, 149, 129, 0])
            expire = int((date(int(str(day)[:4]), int(str(day)[4:6]), int(str(day)[6:])) +
                          timedelta(days=rng.choice([plan_days, 3, 31, 45]))).strftime("%Y%m%d"))
            rows.append((f"m{m}", rng.choice([41, 39, 36]), plan_days, price, price, rng.randint(0, 1),
                         day, expire, int(rng.random() < 0.3)))
    df = spark.createDataFrame(rows, COLS)
    ref = {r.msno: (r.last_expire, r.is_churn) for r in build_cohort_labels(df, 2017, 2).collect()}
    fast = {r.msno: (r.last_expire, r.is_churn) for r in build_cohort_labels_fast(df, 2017, 2).collect()}
    assert len(ref) > 50
    assert fast == ref
