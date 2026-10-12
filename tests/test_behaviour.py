"""P3 arm checks on tiny synthetic sequences (ADR-003)."""

import numpy as np
import pandas as pd
import pytest

from src.models.behaviour import MIN, shape_features


def _fading_and_steady(days=60):
    X = np.zeros((2, days, 7), dtype=np.float16)
    X[0, :, MIN] = np.log1p(np.linspace(60, 0, days))          # fading: 60 → 0 minutes
    X[1, :, MIN] = np.log1p(40)                                # steady 40 minutes a day
    X[1, 20:31, MIN] = 0                                       # one 11-day gap
    X[:, :, 4] = np.where(X[:, :, MIN] > 0, np.log1p(5), 0)    # some full listens on active days
    return X


def test_shape_features_separate_fading_from_steady():
    f = shape_features(_fading_and_steady(), pd.Series([20170301, 20170301]))
    assert f.loc[0, "seq_minutes_slope_60"] < 0 < f.loc[1, "seq_minutes_slope_60"] + 1e-6
    assert f.loc[0, "seq_last7_vs_prior23"] < f.loc[1, "seq_last7_vs_prior23"]
    assert f.loc[1, "seq_longest_gap"] == 11
    assert 0 <= f.loc[1, "seq_weekend_share"] <= 1


def test_masked_autoencoder_learns_and_embeds():
    torch = pytest.importorskip("torch")
    from src.models.behaviour import encode_masked_autoencoder, train_masked_autoencoder
    rng = np.random.default_rng(0)
    X = (rng.random((512, 60, 7)) * 3).astype(np.float16)
    model, mu, sd = train_masked_autoencoder(X, dim=8, epochs=2, batch=128)
    Z = encode_masked_autoencoder(model, mu, sd, X[:10], batch=4)
    assert Z.shape == (10, 8) and np.isfinite(Z).all()
