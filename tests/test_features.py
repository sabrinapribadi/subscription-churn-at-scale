"""Leakage guard (ADR-001): rows on or after the snapshot date must not change any feature."""

import pytest

pytest.importorskip("pyspark")

from src.features.build import add_snapshot, build_features  # noqa: E402
from src.spark_session import get_spark  # noqa: E402

TX = ["msno", "payment_method_id", "payment_plan_days", "plan_list_price", "actual_amount_paid",
      "is_auto_renew", "transaction_date", "membership_expire_date", "is_cancel"]
UL = ["msno", "date", "num_25", "num_50", "num_75", "num_985", "num_100", "num_unq", "total_secs", "year_month"]
MB = ["msno", "city", "bd", "gender", "registered_via", "registration_init_time"]


@pytest.fixture(scope="module")
def spark():
    s = get_spark("test-features", driver_memory="1g")
    yield s
    s.stop()


def _frames(spark, extra_tx=(), extra_ul=()):
    tx = [("a", 41, 30, 149, 149, 1, 20161215, 20170115, 0),
          ("a", 41, 30, 149, 149, 1, 20170114, 20170215, 0)] + list(extra_tx)
    ul = [("a", d, 1, 0, 0, 0, 10, 8, 2400.0, d // 100) for d in (20170105, 20170120, 20170128)] + list(extra_ul)
    mb = [("a", 1, 30, "female", 7, 20150101)]
    cohort = spark.createDataFrame([("a", 201702, 20170215, 0, "official")],
                                   ["msno", "cohort", "last_expire", "label", "label_source"])
    cohort = add_snapshot(cohort, lead_days=14)  # snapshot = 2017-02-01
    return (spark.createDataFrame(tx, TX), spark.createDataFrame(ul, UL), spark.createDataFrame(mb, MB), cohort)


def test_snapshot_is_expiry_minus_k(spark):
    *_, cohort = _frames(spark)
    assert cohort.first().snapshot == 20170201


def test_rows_after_snapshot_do_not_change_features(spark):
    clean = build_features(*_frames(spark), window_days=120).first().asDict()
    leaked = build_features(
        *_frames(
            spark,
            extra_tx=[("a", 99, 410, 1788, 0, 0, 20170201, 20180301, 1), ("a", 99, 7, 0, 0, 0, 20170210, 20170217, 1)],
            extra_ul=[("a", 20170201, 999, 0, 0, 0, 999, 999, 86400.0, 201702), ("a", 20170214, 0, 0, 0, 0, 0, 1, 50.0, 201702)],
        ),
        window_days=120,
    ).first().asDict()
    assert leaked == clean


def test_recent_window_and_counts(spark):
    f = build_features(*_frames(spark), window_days=120).first()
    assert f.tx_count == 2 and f.last_plan_days == 30 and f.last_auto_renew == 1
    assert f.use_active_days == 3 and f.use_active_days_recent == 2  # 01-20 and 01-28 fall in [01-18, 02-01)
    assert f.days_since_last_play == 4 and f.gender == 2


@pytest.mark.parametrize("window", [30, 120])
def test_multi_window_matches_single_window(spark, window):
    from src.features.build import build_features_multi, select_window
    frames = _frames(spark, extra_ul=[("a", 20161201, 2, 1, 0, 0, 5, 6, 1500.0, 201612)])
    single = build_features(*frames, window_days=window).first().asDict()
    multi = build_features_multi(*frames, windows=[30, 60, 120]).first().asDict()
    mapped = {target: multi[src] for src, target in select_window(list(multi), window).items()}
    assert set(mapped) == set(single)
    for k, v in single.items():
        assert mapped[k] == pytest.approx(v, rel=1e-9, abs=1e-12), k


def test_last_transaction_is_one_row_even_on_ties(spark):
    """ADR-008: two transactions with the same date and expiry used to give run-dependent, mixed fields."""
    tie = [("a", 36, 30, 99, 99, 0, 20170114, 20170215, 1)]  # same day and expiry as the second base row, but a cancellation
    want = {"last_payment_method": 36, "last_plan_days": 30, "last_list_price": 99, "last_amount_paid": 99,
            "last_auto_renew": 0, "last_is_cancel": 1}
    for order in (tie, tie[::-1]):
        tx, ul, mb, cohort = _frames(spark, extra_tx=order)
        for parts in (1, 4):  # partitioning must not change the answer
            row = build_features(tx.repartition(parts), ul, mb, cohort, window_days=30).first().asDict()
            assert {k: row[k] for k in want} == want


def test_feature_columns_are_in_a_fixed_order():
    import pandas as pd

    from src.models.baseline import feature_columns
    a = pd.DataFrame(columns=["msno", "label", "tx_count", "age", "cohort", "last_plan_days"])
    assert feature_columns(a) == feature_columns(a[a.columns[::-1]]) == ["age", "last_plan_days", "tx_count"]


def test_rows_are_in_a_fixed_order():
    import pandas as pd

    from src.models.baseline import canonical_rows
    a = pd.DataFrame({"msno": ["b", "a", "c", "a"], "cohort": [201703, 201703, 201702, 201702], "x": [1, 2, 3, 4]})
    assert canonical_rows(a).equals(canonical_rows(a.sample(frac=1, random_state=3)))
    assert list(canonical_rows(a)["x"]) == [4, 3, 2, 1]
