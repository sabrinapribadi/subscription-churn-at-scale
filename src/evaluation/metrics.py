"""Shared evaluation for every phase (ADR-002): PR-AUC primary, capture and precision at the call budget."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def top_k_metrics(y: np.ndarray, p: np.ndarray, frac: float) -> dict:
    k = int(len(y) * frac)
    idx = np.argsort(-p)[:k]
    prec = y[idx].mean()
    return {"precision_at_k": float(prec), "recall_at_k": float(y[idx].sum() / y.sum()), "lift_at_k": float(prec / y.mean())}


def evaluate(y: np.ndarray, p: np.ndarray, frac: float) -> dict:
    out = {"pr_auc": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p)),
           "base_rate": float(y.mean()), "n": int(len(y))}
    if p.min() >= 0 and p.max() <= 1:
        out |= {"log_loss": float(log_loss(y, np.clip(p, 1e-7, 1 - 1e-7))), "brier": float(brier_score_loss(y, p))}
    return out | top_k_metrics(y, p, frac)
