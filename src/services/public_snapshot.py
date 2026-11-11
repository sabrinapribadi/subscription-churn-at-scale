"""Snapshot for the public demo API (ADR-010): aggregates of the real call list plus synthetic demo members.

The competition's data terms forbid redistribution, so no real member row leaves the laptop:
- call-list totals at every 0.1% of members (members called, expected churners, value at risk) for the real cohort;
- what-if curves (already aggregate, from P4);
- 100 synthetic members (real feature schema, made-up values) scored, ranked and explained by the real model.
"""

from __future__ import annotations

import numpy as np

from src.data.synthetic import synthetic_cohort
from src.genai.explain import Explainer
from src.models.baseline import prepare
from src.models.ranking import member_value
from src.services.contracts import Score
from src.services.store import ServingStore, apply_calibration, risk_level

GRID = 1000                       # call-list totals at every 0.1% of members
DEMO_N, DEMO_SEED = 100, 2026


def call_grid(store: ServingStore) -> dict:
    """Cumulative totals of the real call list (ordered as ServingStore.call_list) at k = floor(n × share)."""
    n = len(store.df)
    top = store.df.loc[store.order]
    cp = np.concatenate([[0.0], np.cumsum(top["_p"].to_numpy())])
    cev = np.concatenate([[0.0], np.cumsum(top["_ev"].to_numpy())])
    ks = [max(1, int(n * (i / GRID))) for i in range(1, GRID + 1)]
    return {"members": n, "k": ks, "expected_churners": [round(float(cp[k]), 1) for k in ks],
            "expected_value_at_risk": [round(float(cev[k]), 0) for k in ks]}


def demo_members(store: ServingStore, explainer: Explainer, n: int = DEMO_N, seed: int = DEMO_SEED) -> dict:
    """Synthetic members scored by the real model; rank and percentile against the real cohort's expected values."""
    d = prepare(synthetic_cohort(n, 201703, seed))
    d["msno"] = [f"demo-{i:03d}" for i in range(1, n + 1)]
    d["member_value"] = member_value(d)
    x = d[store.features]
    for c in x.columns:                               # same categories as the store, so the booster reads them alike
        if str(store.df[c].dtype) == "category":
            x[c] = x[c].astype(int).astype(store.df[c].dtype)
    p = apply_calibration(store.booster.predict(x), store.cal)
    ev = p * d["member_value"].to_numpy(dtype=float)
    real = np.sort(store.df["_ev"].to_numpy())
    N = len(real); out = {}
    for i, mid in enumerate(d["msno"]):
        rank = int(N - np.searchsorted(real, ev[i], side="right")) + 1          # members in the real cohort above it, + 1
        s = Score(member_id=mid, churn_probability=float(p[i]), risk_level=risk_level(float(p[i])), member_value=float(d["member_value"].iloc[i]),
                  expected_value_at_risk=float(ev[i]), priority_rank=rank, priority_percentile=round(100 * (1 - (rank - 1) / N), 2),
                  expiry_date=int(d["last_expire"].iloc[i]), model_version=store.model_version)
        e = explainer.explain(s, store.reasons_for(mid, x.iloc[[i]]))
        out[mid] = {"score": s.model_dump(), "explanation": e.model_dump()}
    return out


def build(store: ServingStore, explainer: Explainer, built: str) -> dict:
    demo = demo_members(store, explainer)
    meters = [v["explanation"]["meter"] for v in demo.values()]
    live = [m for m in meters if m["provider"] != "template"]
    return {"version": 1, "built": built, "model_version": store.model_version,
            "data_terms": "Aggregates of the real cohort only; members are synthetic (competition data is not redistributed).",
            "call_grid": call_grid(store), "scenarios": store.scenarios, "demo": demo,
            "notes": {"provider": explainer.provider.name, "model": explainer.provider.model, "live_calls": len(live),
                      "grounded": sum(v["explanation"]["grounded"] for v in demo.values()),
                      "cost_usd": round(sum(m["cost_usd"] for m in live), 6),
                      "p95_ms_live": round(float(np.percentile([m["latency_ms"] for m in live], 95)), 1) if live else None}}
