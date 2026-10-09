"""Unit tests for the label port — one test per rule commented in the official labeller."""

from src.data.labels import Txn, is_churn, last_expire, order_transactions, renewal_gap


def t(date, expire, cancel=0, price=149, days=30, method=41):
    return Txn(method, days, price, date, expire, cancel)


def test_later_transaction_date_sorts_last():
    a, b = t(20170105, 20170205), t(20170110, 20170210)
    assert order_transactions([b, a]) == [a, b]


def test_same_day_same_plan_subscribe_precedes_cancel():
    sub, cancel = t(20170110, 20170210), t(20170110, 20170115, cancel=1)
    assert order_transactions([cancel, sub]) == [sub, cancel]
    assert last_expire([cancel, sub]) == 20170115


def test_same_day_consecutive_renewals_keep_extending():
    r1, r2 = t(20170110, 20170210), t(20170110, 20170310)
    assert last_expire([r2, r1]) == 20170310


def test_same_day_consecutive_cancels_move_expiry_earlier():
    c1, c2 = t(20170110, 20170205, cancel=1), t(20170110, 20170201, cancel=1)
    assert order_transactions([c2, c1]) == [c1, c2]


def test_same_day_different_plans_use_string_signature_descending():
    # Signatures compare as strings: "993041" > "1493041" because "9" > "1",
    # so the 99-price plan sorts first even though 99 < 149 numerically.
    cheap, dear = t(20170110, 20170210, price=99), t(20170110, 20170210, price=149)
    assert order_transactions([dear, cheap]) == [cheap, dear]


def test_no_future_activity_is_churn():
    assert is_churn([], 20170215) is True


def test_renewal_within_30_days_is_not_churn():
    assert renewal_gap([t(20170301, 20170401)], 20170215) == 14
    assert is_churn([t(20170301, 20170401)], 20170215) is False


def test_renewal_exactly_30_days_late_is_churn():
    assert is_churn([t(20170317, 20170417)], 20170215) is True


def test_cancel_then_renewal_measures_gap_from_cancelled_expiry():
    cancel = t(20170201, 20170205, cancel=1)
    renew = t(20170310, 20170410)
    assert renewal_gap([cancel, renew], 20170228) == 33
    assert is_churn([cancel, renew], 20170228) is True


def test_only_cancels_in_future_is_churn():
    assert is_churn([t(20170201, 20170205, cancel=1)], 20170228) is True
