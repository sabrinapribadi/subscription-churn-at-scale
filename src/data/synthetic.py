"""Synthetic members with the real feature schema (no real data). Used by the tests and by the public demo (ADR-010)."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["tx_count", "tx_cancels", "tx_auto_renew_share", "tx_mean_discount", "tx_distinct_methods", "last_plan_days",
            "last_list_price", "last_amount_paid", "last_auto_renew", "last_payment_method", "last_is_cancel", "tenure_days",
            "days_since_last_tx", "tx_count_window", "tx_cancels_window", "use_active_days_recent", "use_secs_per_day_recent",
            "use_active_days", "use_secs", "use_unique_songs_mean", "use_secs_per_day", "use_decline_ratio",
            "use_full_listen_share", "use_skip_share", "days_since_last_play", "city", "gender", "registered_via", "age",
            "registration_days"]


def synthetic_cohort(n: int, cohort: int, seed: int) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    auto = (r.random(n) < 0.85).astype(int)
    cancel = (r.random(n) < 0.05).astype(int)
    idle = r.integers(0, 31, n)
    plan = r.choice([30, 30, 30, 90, 410], n)
    price = np.where(plan == 30, r.choice([99, 149], n), np.where(plan == 90, 298, 1788))
    df = pd.DataFrame({
        "msno": [f"m{cohort}_{i:05d}" for i in range(n)], "cohort": cohort, "snapshot": 20170201 if cohort == 201702 else 20170301,
        "last_expire": 20170215 if cohort == 201702 else 20170315,
        "tx_count": r.integers(1, 30, n), "tx_cancels": r.integers(0, 3, n), "tx_auto_renew_share": auto * r.uniform(0.6, 1, n),
        "tx_mean_discount": r.integers(0, 20, n), "tx_distinct_methods": r.integers(1, 3, n), "last_plan_days": plan,
        "last_list_price": price, "last_amount_paid": price, "last_auto_renew": auto, "last_payment_method": r.choice([36, 39, 41], n),
        "last_is_cancel": cancel, "tenure_days": r.integers(30, 900, n), "days_since_last_tx": r.integers(0, 40, n),
        "tx_count_window": r.integers(0, 3, n), "tx_cancels_window": cancel, "use_active_days_recent": r.integers(0, 15, n),
        "use_secs_per_day_recent": r.uniform(0, 5000, n), "use_active_days": r.integers(0, 31, n), "use_secs": r.uniform(0, 150000, n),
        "use_unique_songs_mean": r.uniform(1, 40, n), "use_secs_per_day": r.uniform(0, 5000, n), "use_decline_ratio": r.uniform(0, 2, n),
        "use_full_listen_share": r.uniform(0, 1, n), "use_skip_share": r.uniform(0, 1, n), "days_since_last_play": idle.astype(float),
        "city": r.choice([1, 5, 13], n), "gender": r.choice([0, 1, 2], n), "registered_via": r.choice([3, 7, 9], n),
        "age": r.integers(15, 60, n).astype(float), "registration_days": r.integers(100, 3000, n),
    })
    logit = -3 + 2.2 * (1 - auto) + 3 * cancel + 0.05 * idle
    df["label"] = (r.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df
