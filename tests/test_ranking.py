"""P4 building blocks (ADR-004)."""

import numpy as np
import pandas as pd

from src.models.ranking import ece, member_value, prior_shift_em, profit_at, query_groups, relevance


def test_member_value_annualises_and_falls_back_to_list_price():
    df = pd.DataFrame({"last_plan_days": [30, 410, 30], "last_amount_paid": [149, 1788, 0], "last_list_price": [149, 1788, 99]})
    v = member_value(df)
    assert v[0] == np.float64(149 / 30 * 365) and round(v[1]) == round(1788 / 410 * 365) and v[2] == 99 / 30 * 365


def test_prior_shift_em_recovers_a_higher_churn_rate():
    rng = np.random.default_rng(0)
    # calibrated scores for a world with 5% churn; true new world has 10% churn
    n, pi_old, pi_new = 200_000, 0.05, 0.10
    y = (rng.random(n) < pi_new).astype(int)
    s = np.where(y == 1, rng.normal(1.5, 1, n), rng.normal(0, 1, n))
    lik1, lik0 = np.exp(-(s - 1.5) ** 2 / 2), np.exp(-s ** 2 / 2)
    p_old = pi_old * lik1 / (pi_old * lik1 + (1 - pi_old) * lik0)   # calibrated for the old prior
    p_new, pi_hat = prior_shift_em(p_old, pi_old)
    assert abs(pi_hat - pi_new) < 0.01
    assert ece(y, p_new) < ece(y, p_old)


def test_relevance_grades_only_churners_by_value():
    r = relevance(np.array([0, 1, 1, 1]), np.array([5000, 100, 1500, 3000]), (1000, 2000))
    assert r.tolist() == [0, 1, 2, 3]


def test_query_groups_cover_every_row_once():
    order, sizes = query_groups(2500, 1000)
    assert sorted(order.tolist()) == list(range(2500)) and sizes == [1000, 1000, 500]


def test_profit_counts_saved_revenue_minus_contact_cost():
    score, y, v = np.array([0.9, 0.8, 0.1, 0.05]), np.array([1, 0, 1, 0]), np.array([1000.0, 1000.0, 1000.0, 1000.0])
    r = profit_at(score, y, v, frac=0.5, save_rate=0.2, contact_cost=20)
    assert r["profit"] == 0.2 * 1000 - 2 * 20 and r["churners_reached"] == 0.5
