"""PSI (ADR-009): zero for identical data, hand-computed value for a known shift, bands, missing values."""

import numpy as np
import pandas as pd
import pytest

from src.monitoring.drift import band, psi, psi_table


def test_identical_distributions_have_zero_psi():
    x = pd.Series(np.random.default_rng(1).normal(size=5000))
    assert psi(x, x) == pytest.approx(0.0, abs=1e-12)


def test_known_shift_matches_hand_calculation():
    ref = pd.Series(["a"] * 50 + ["b"] * 50)
    cur = pd.Series(["a"] * 80 + ["b"] * 20)
    want = (0.8 - 0.5) * np.log(0.8 / 0.5) + (0.2 - 0.5) * np.log(0.2 / 0.5)
    assert psi(ref, cur) == pytest.approx(want, rel=1e-6)


def test_mean_shift_is_flagged_and_noise_is_not():
    r = np.random.default_rng(2)
    ref = pd.Series(r.normal(size=20000))
    assert band(psi(ref, pd.Series(r.normal(size=20000)))) == "stable"
    assert band(psi(ref, pd.Series(r.normal(loc=1.0, size=20000)))) == "alert"


def test_missing_values_get_their_own_bin():
    ref = pd.Series(np.r_[np.arange(1000, dtype=float), [np.nan] * 10])
    cur = pd.Series(np.r_[np.arange(1000, dtype=float), [np.nan] * 300])
    assert psi(ref, cur) > psi(ref, ref) + 0.1


def test_table_covers_every_column_and_bands():
    r = np.random.default_rng(3)
    a = pd.DataFrame({"x": r.normal(size=3000), "g": pd.Categorical(r.choice([1, 2, 3], 3000))})
    b = pd.DataFrame({"x": r.normal(loc=2, size=3000), "g": pd.Categorical(r.choice([1, 2, 3], 3000))})
    t = psi_table(a, b, ["x", "g"])
    assert set(t.feature) == {"x", "g"} and t.iloc[0].feature == "x" and t.iloc[0].band == "alert"
