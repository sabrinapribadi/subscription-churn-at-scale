"""Churn label reconstruction — a faithful port of the official WSDM Cup 2018 labeller.

The official labeller (WSDMChurnLabeller.scala, shipped with the competition data) decides,
for one target month M:

1. History = transactions dated within the calendar month before M.
   Each member's last expiry is the expire date of the *last* history transaction
   after a custom ordering (``_order_key``).
2. Candidates = members whose last expiry falls inside M.
3. Future = transactions dated after the history window.
   Walk future transactions in the same order: a cancel can only move the expiry
   earlier; the first non-cancel transaction is the renewal. gap = renewal − expiry (days).
4. is_churn = no future transaction, or no renewal, or gap >= 30.

The ordering intentionally reproduces the Scala comparator, including its string
comparison of ``plan_list_price + payment_plan_days + payment_method_id``, so that our
labels can be validated against the official ones (ADR-001, P0 gate >= 99% agreement).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cmp_to_key
from typing import Iterable, Sequence

CHURN_GAP_DAYS = 30
NO_RENEWAL = 9999


@dataclass(frozen=True)
class Txn:
    payment_method_id: int
    payment_plan_days: int
    plan_list_price: int
    transaction_date: int  # yyyymmdd
    membership_expire_date: int  # yyyymmdd
    is_cancel: int


def _sig(t: Txn) -> str:
    # Scala concatenates the raw CSV strings, then compares them as strings.
    return f"{t.plan_list_price}{t.payment_plan_days}{t.payment_method_id}"


def _lt(x: Txn, y: Txn) -> bool:
    """The Scala ``sortWith`` less-than: True if x must come before y."""
    if x.transaction_date != y.transaction_date:
        return x.transaction_date < y.transaction_date  # yyyymmdd: int order == string order
    xs, ys = _sig(x), _sig(y)
    if xs != ys:
        return xs > ys  # string comparison, descending — kept for label parity
    if x.is_cancel == 1 and y.is_cancel == 1:
        # consecutive cancels only move the expiry earlier: later expiry first
        return x.membership_expire_date > y.membership_expire_date
    if x.is_cancel == 0 and y.is_cancel == 0:
        # consecutive renewals keep extending: earlier expiry first
        return x.membership_expire_date < y.membership_expire_date
    # same day, same plan: subscription precedes cancellation
    return x.is_cancel < y.is_cancel


def _compare(x: Txn, y: Txn) -> int:
    # Both Scala's sortWith and Python's sorted are stable, so full ties keep input order.
    if _lt(x, y):
        return -1
    return 1 if _lt(y, x) else 0


def order_transactions(txns: Iterable[Txn]) -> list[Txn]:
    return sorted(txns, key=cmp_to_key(_compare))


def last_expire(history: Sequence[Txn]) -> int:
    """Expire date of the last history transaction after official ordering."""
    return order_transactions(history)[-1].membership_expire_date


def _to_date(yyyymmdd: int) -> date:
    s = str(yyyymmdd)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def renewal_gap(future: Sequence[Txn], expire: int) -> int:
    """Days from (possibly cancel-adjusted) expiry to the first renewal; 9999 if none."""
    current_expire = _to_date(expire)
    for t in order_transactions(future):
        if t.is_cancel == 1:
            e = _to_date(t.membership_expire_date)
            if e < current_expire:
                current_expire = e
        else:
            return (_to_date(t.transaction_date) - current_expire).days
    return NO_RENEWAL


def is_churn(future: Sequence[Txn], expire: int) -> bool:
    if not future:
        return True
    return renewal_gap(future, expire) >= CHURN_GAP_DAYS
