"""Plain-language names for model features, so reasons read like a CRM note, not a column name."""

from __future__ import annotations

import math

SENSITIVE = {"gender", "age", "city"}  # never quoted to agents (still used and shown in technical views)

_LABELS = {
    "last_auto_renew": ("auto-renew", lambda v: "on" if v >= 0.5 else "off"),
    "last_is_cancel": ("last transaction was a cancellation", lambda v: "yes" if v >= 0.5 else "no"),
    "last_payment_method": ("payment method", lambda v: f"type {int(v)}"),
    "days_since_last_tx": ("days since last payment", lambda v: f"{int(round(v))}"),
    "tenure_days": ("days as a paying member", lambda v: f"{int(round(v))}"),
    "registration_days": ("days since sign-up", lambda v: f"{int(round(v))}"),
    "tx_count": ("payments to date", lambda v: f"{int(round(v))}"),
    "tx_count_window": ("payments in the last 30 days", lambda v: f"{int(round(v))}"),
    "tx_cancels": ("cancellations to date", lambda v: f"{int(round(v))}"),
    "tx_cancels_window": ("cancellations in the last 30 days", lambda v: f"{int(round(v))}"),
    "tx_auto_renew_share": ("share of payments on auto-renew", lambda v: f"{round(100 * v)}%"),
    "tx_mean_discount": ("average discount per payment", lambda v: f"{int(round(v))}"),
    "tx_distinct_methods": ("payment methods used", lambda v: f"{int(round(v))}"),
    "last_plan_days": ("plan length in days", lambda v: f"{int(round(v))}"),
    "last_list_price": ("plan list price", lambda v: f"{int(round(v))}"),
    "last_amount_paid": ("last amount paid", lambda v: f"{int(round(v))}"),
    "use_active_days": ("listening days in the last 30", lambda v: f"{int(round(v))}"),
    "use_active_days_recent": ("listening days in the last 14", lambda v: f"{int(round(v))}"),
    "days_since_last_play": ("days since last listened", lambda v: f"{int(round(v))}"),
    "use_secs": ("minutes listened in the last 30 days", lambda v: f"{int(round(v / 60))}"),
    "use_secs_per_day": ("minutes per day, last 30 days", lambda v: f"{int(round(v / 60))}"),
    "use_secs_per_day_recent": ("minutes per day, last 14 days", lambda v: f"{int(round(v / 60))}"),
    "use_decline_ratio": ("recent vs usual listening", lambda v: f"{v:.2f}x"),
    "use_full_listen_share": ("songs played to the end", lambda v: f"{round(100 * v)}%"),
    "use_skip_share": ("songs skipped early", lambda v: f"{round(100 * v)}%"),
    "use_unique_songs_mean": ("unique songs per listening day", lambda v: f"{v:.1f}"),
    "registered_via": ("sign-up channel", lambda v: f"type {int(v)}"),
    "city": ("city", lambda v: f"code {int(v)}"),
    "gender": ("gender", lambda v: {0: "unknown", 1: "male", 2: "female"}.get(int(v), "unknown")),
    "age": ("age", lambda v: f"{int(round(v))}"),
}


def is_sensitive(feature: str) -> bool:
    return feature in SENSITIVE


def describe(feature: str, value) -> tuple[str, str]:
    label, fmt = _LABELS.get(feature, (feature.replace("_", " "), lambda v: f"{v:g}"))
    try:
        missing = value is None or (isinstance(value, float) and math.isnan(value))
    except TypeError:
        missing = False
    if missing:
        return label, "no data"
    try:
        return label, fmt(float(value))
    except (TypeError, ValueError):
        return label, str(value)
