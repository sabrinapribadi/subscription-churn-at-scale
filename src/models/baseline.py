"""LightGBM baseline shared by P1 and P2 (same parameters, same early-stopping split)."""

from __future__ import annotations

import lightgbm as lgb
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from src.features.schema import CATEGORICAL

NON_FEATURES = {"msno", "cohort", "last_expire", "snapshot", "label", "label_source"}
PARAMS = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_child_samples=200,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
              n_estimators=3000, verbose=-1, random_state=7)


def feature_columns(data: pd.DataFrame) -> list[str]:
    """Model inputs in a fixed (alphabetical) order. LightGBM samples columns by position (feature_fraction),
    so the same features in a different column order train a different model (ADR-008)."""
    return sorted(c for c in data.columns if c not in NON_FEATURES)


def canonical_rows(data: pd.DataFrame) -> pd.DataFrame:
    """Rows in a fixed order (cohort, member). Spark writes rows in a platform-dependent order, and LightGBM's
    bagging samples rows by position, so the same rows in a different order train a different model (ADR-008)."""
    return data.sort_values(["cohort", "msno"], kind="mergesort").reset_index(drop=True)


def prepare(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data["cohort"] = data["cohort"].astype(int)
    for c in CATEGORICAL:
        data[c] = data[c].fillna(-1).astype(int).astype("category")
    return data


def holdout_split(train: pd.DataFrame):
    """The 90/10 member-grouped split used for early stopping (deterministic)."""
    gss = GroupShuffleSplit(n_splits=1, test_size=0.1, random_state=7)
    return next(gss.split(train, groups=train["msno"]))


def fit(train: pd.DataFrame, features: list[str]) -> lgb.LGBMClassifier:
    """Early stopping on a 10% member-level hold-out inside the training cohorts."""
    tr_idx, va_idx = holdout_split(train)
    tr, va = train.iloc[tr_idx], train.iloc[va_idx]
    model = lgb.LGBMClassifier(**PARAMS)
    model.fit(tr[features], tr["label"], eval_set=[(va[features], va["label"])], eval_metric="average_precision",
              callbacks=[lgb.early_stopping(100, verbose=False)])
    return model
