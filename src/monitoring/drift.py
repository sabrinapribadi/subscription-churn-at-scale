"""Population Stability Index per feature and for the score (ADR-009).

PSI = Σ (a − e) · ln(a / e) over bins of the reference cohort, where e and a are the shares of the
reference and current cohorts in each bin. Numeric features use reference quantile bins; features
with few distinct values (or categories) use one bin per value. Missing values get their own bin.
Bands follow the usual scorecard convention: < 0.10 stable, 0.10–0.25 watch, > 0.25 alert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STABLE, ALERT = 0.10, 0.25
FLOOR = 1e-4  # share given to empty bins, so ln() stays finite


def band(value: float) -> str:
    return "alert" if value > ALERT else "watch" if value >= STABLE else "stable"


def _shares(codes: np.ndarray, n_bins: int) -> np.ndarray:
    counts = np.bincount(codes, minlength=n_bins).astype(float)
    shares = counts / max(counts.sum(), 1.0)
    return np.maximum(shares, FLOOR)


def psi(reference: pd.Series, current: pd.Series, bins: int = 10, max_levels: int = 20) -> float:
    ref, cur = pd.Series(reference), pd.Series(current)
    if isinstance(ref.dtype, pd.CategoricalDtype) or ref.nunique(dropna=True) <= max_levels:
        levels = pd.Index(pd.concat([ref, cur]).dropna().unique())
        map_ = {v: i for i, v in enumerate(levels)}
        rc = ref.astype(object).map(map_).fillna(len(levels)).astype(int).to_numpy()
        cc = cur.astype(object).map(map_).fillna(len(levels)).astype(int).to_numpy()
        n = len(levels) + 1
    else:
        edges = np.unique(np.nanquantile(ref.to_numpy(dtype=float), np.linspace(0, 1, bins + 1))[1:-1])
        def code(x):
            v = x.to_numpy(dtype=float)
            c = np.searchsorted(edges, v, side="right")
            c[np.isnan(v)] = len(edges) + 1  # missing bin
            return c
        rc, cc, n = code(ref), code(cur), len(edges) + 2
    e, a = _shares(rc, n), _shares(cc, n)
    return float(np.sum((a - e) * np.log(a / e)))


def psi_table(reference: pd.DataFrame, current: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows = []
    for c in columns:
        v = psi(reference[c], current[c])
        num = lambda s: pd.to_numeric(s.astype("float64") if isinstance(s.dtype, pd.CategoricalDtype) else s, errors="coerce")  # noqa: E731
        rows.append({"feature": c, "psi": round(v, 4), "band": band(v),
                     "reference_mean": float(num(reference[c]).mean()), "current_mean": float(num(current[c]).mean()),
                     "reference_missing": float(reference[c].isna().mean()), "current_missing": float(current[c].isna().mean())})
    return pd.DataFrame(rows).sort_values("psi", ascending=False).reset_index(drop=True)
