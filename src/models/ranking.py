"""P4 (ADR-004): member value, calibration under a shifted churn rate, LambdaMART, and profit at k."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

RANK_PARAMS = dict(objective="lambdarank", learning_rate=0.05, num_leaves=63, min_child_samples=200,
                   feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
                   n_estimators=2000, verbose=-1, random_state=7)


def member_value(df: pd.DataFrame, horizon_days: int = 365) -> np.ndarray:
    """Revenue if retained: amount paid per day of the last plan × horizon (list price when paid = 0)."""
    days = df["last_plan_days"].replace(0, np.nan)
    paid = df["last_amount_paid"].where(df["last_amount_paid"] > 0, df["last_list_price"])
    v = (paid / days * horizon_days).fillna(0).to_numpy(dtype=float)
    return np.clip(v, 0, None)


# ---------------------------------------------------------------------------- calibration
def fit_isotonic(p: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    return IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, out_of_bounds="clip").fit(p, y)


def prior_shift_em(p: np.ndarray, prior_train: float, tol: float = 1e-6, max_iter: int = 500) -> tuple[np.ndarray, float]:
    """Saerens et al. (2002): re-estimate the new churn rate from unlabelled calibrated scores and adjust them."""
    pi = prior_train
    for _ in range(max_iter):
        a, b = pi / prior_train, (1 - pi) / (1 - prior_train)
        q = a * p / (a * p + b * (1 - p))
        new = float(q.mean())
        if abs(new - pi) < tol:
            pi = new
            break
        pi = new
    a, b = pi / prior_train, (1 - pi) / (1 - prior_train)
    return a * p / (a * p + b * (1 - p)), pi


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error over equal-size groups (same binning as the practitioner report)."""
    order = np.argsort(p, kind="stable")
    err = 0.0
    for chunk in np.array_split(order, bins):
        err += len(chunk) / len(p) * abs(p[chunk].mean() - y[chunk].mean())
    return float(err)


# ---------------------------------------------------------------------------- ranking
def relevance(y: np.ndarray, value: np.ndarray, cuts: tuple[float, float]) -> np.ndarray:
    """0 for members who stay; churners graded 1–3 by value tercile (cuts from training churners)."""
    grade = 1 + (value > cuts[0]).astype(int) + (value > cuts[1]).astype(int)
    return np.where(y == 1, grade, 0)


def query_groups(n: int, size: int, seed: int = 7) -> tuple[np.ndarray, list[int]]:
    """Random order of n rows and the group sizes LightGBM's ranker expects."""
    order = np.random.default_rng(seed).permutation(n)
    sizes = [size] * (n // size) + ([n % size] if n % size else [])
    return order, sizes


def fit_lambdamart(tr: pd.DataFrame, va: pd.DataFrame, features: list[str], rel_tr: np.ndarray, rel_va: np.ndarray,
                   group_size: int = 1000) -> lgb.LGBMRanker:
    o_tr, g_tr = query_groups(len(tr), group_size)
    o_va, g_va = query_groups(len(va), group_size, seed=8)
    model = lgb.LGBMRanker(**RANK_PARAMS)
    model.fit(tr[features].iloc[o_tr], rel_tr[o_tr], group=g_tr,
              eval_set=[(va[features].iloc[o_va], rel_va[o_va])], eval_group=[g_va], eval_at=[100],
              callbacks=[lgb.early_stopping(100, verbose=False)])
    return model


# ---------------------------------------------------------------------------- profit
def profit_at(score: np.ndarray, y: np.ndarray, value: np.ndarray, frac: float, save_rate: float, contact_cost: float) -> dict:
    k = int(len(score) * frac)
    top = np.argsort(-score, kind="stable")[:k]
    saved = save_rate * (y[top] * value[top]).sum()
    return {"profit": float(saved - contact_cost * k), "revenue_saved": float(saved), "contact_cost": float(contact_cost * k),
            "churners_reached": float(y[top].sum() / y.sum()),
            "value_at_risk_reached": float((y[top] * value[top]).sum() / (y * value).sum())}


def profit_curve(score: np.ndarray, y: np.ndarray, value: np.ndarray, save_rate: float, contact_cost: float,
                 fractions=np.arange(0.01, 0.51, 0.01)) -> list[list[float]]:
    order = np.argsort(-score, kind="stable")
    gain = np.cumsum(save_rate * y[order] * value[order] - contact_cost)
    return [[round(float(f), 2), round(float(gain[int(len(score) * f) - 1]), 0)] for f in fractions]
