"""Serving store: loads versioned artefacts and answers scoring questions (ADR-005).

Artefacts (written by scripts/export_serving_artifacts.py, or by tests on synthetic data):
  model.txt          LightGBM booster
  calibration.json   isotonic thresholds + prior shift + model version + feature list
  features.parquet   one row per member: msno, cohort, snapshot, last_expire, features, member_value
  scenarios.json     value-by-budget curves for what-if questions (from P4)
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.features.schema import CATEGORICAL
from src.genai.dictionary import describe, is_sensitive
from src.services.contracts import CallList, CallListRequest, CallListSummary, MemberFeatures, Reason, Reasons, Score, WhatIf

HIGH, MEDIUM = 0.30, 0.10


def risk_level(p: float) -> str:
    return "high" if p >= HIGH else "medium" if p >= MEDIUM else "low"


def apply_calibration(raw: np.ndarray, cal: dict) -> np.ndarray:
    iso = np.interp(raw, cal["iso_x"], cal["iso_y"])
    a, b = cal["prior_new"] / cal["prior_train"], (1 - cal["prior_new"]) / (1 - cal["prior_train"])
    return a * iso / (a * iso + b * (1 - iso))


class ServingStore:
    def __init__(self, serving_dir: str | Path):
        d = Path(serving_dir)
        self.cal = json.loads((d / "calibration.json").read_text())
        self.model_version = self.cal["model_version"]
        self.features = list(self.cal["features"])
        self.booster = lgb.Booster(model_file=str(d / "model.txt"))
        df = pd.read_parquet(d / "features.parquet")
        for c in CATEGORICAL:
            if c in df:
                df[c] = df[c].fillna(-1).astype(int).astype("category")
        self.df = df.set_index("msno")
        raw = self.booster.predict(self.df[self.features])
        p = apply_calibration(raw, self.cal)
        v = self.df["member_value"].to_numpy(dtype=float)
        ev = p * v
        order = np.lexsort((-raw, -ev))  # by expected value, ties by raw score (ADR-004)
        rank = np.empty(len(order), dtype=int); rank[order] = np.arange(1, len(order) + 1)
        self.df = self.df.assign(_raw=raw, _p=p, _ev=ev, _rank=rank)
        self.order = self.df.index.to_numpy()[order]
        sc = d / "scenarios.json"
        self.scenarios = json.loads(sc.read_text()) if sc.exists() else None

    # ------------------------------------------------------------------ lookups
    def _row(self, member_id: str) -> pd.Series:
        if member_id not in self.df.index:
            raise KeyError(member_id)
        return self.df.loc[member_id]

    def member_features(self, member_id: str) -> MemberFeatures:
        r = self._row(member_id)
        feats = {f: (None if pd.isna(r[f]) else float(r[f])) for f in self.features}
        return MemberFeatures(member_id=member_id, cohort=int(r["cohort"]), snapshot_date=int(r["snapshot"]),
                              expiry_date=int(r["last_expire"]), features=feats)

    def score(self, member_id: str) -> Score:
        r = self._row(member_id)
        n = len(self.df)
        return Score(member_id=member_id, churn_probability=float(r["_p"]), risk_level=risk_level(float(r["_p"])),
                     member_value=float(r["member_value"]), expected_value_at_risk=float(r["_ev"]),
                     priority_rank=int(r["_rank"]), priority_percentile=round(100 * (1 - (int(r["_rank"]) - 1) / n), 2),
                     expiry_date=int(r["last_expire"]), model_version=self.model_version)

    def reasons(self, member_id: str, k: int = 5) -> Reasons:
        self._row(member_id)
        x = self.df.loc[[member_id], self.features]
        contrib = self.booster.predict(x, pred_contrib=True)[0][:-1]  # last column is the bias term
        top = np.argsort(-np.abs(contrib))[:k]
        out = []
        for j in top:
            f = self.features[j]
            label, value = describe(f, x.iloc[0][f])
            out.append(Reason(feature=f, label=label, value=value, contribution=round(float(contrib[j]), 4),
                              direction="raises risk" if contrib[j] > 0 else "lowers risk", shown_to_agent=not is_sensitive(f)))
        return Reasons(member_id=member_id, reasons=out, model_version=self.model_version)

    def call_list(self, req: CallListRequest) -> CallList:
        k = max(1, int(len(self.df) * req.share))  # same count as P4 (floor)
        top = self.df.loc[self.order[:k]]
        ev = float(top["_ev"].sum())
        summary = CallListSummary(members_called=k, expected_churners=round(float(top["_p"].sum()), 1),
                                  expected_value_at_risk=round(ev, 0), expected_profit=round(req.save_rate * ev - req.cost_per_call * k, 0))
        return CallList(request=req, summary=summary, members=[self.score(m) for m in self.order[: min(req.limit, k)]])

    def what_if(self, save_rate: float, cost_per_call: float) -> WhatIf:
        if not self.scenarios:
            raise KeyError("scenarios")
        n, curves = self.scenarios["members"], self.scenarios["value_curves"]
        prof = {k: [(f, save_rate * v - cost_per_call * n * f) for f, v in c] for k, c in curves.items()}
        best = max(prof["expected_value"], key=lambda q: q[1])
        at10 = {k: round(next(p for f, p in c if abs(f - 0.10) < 1e-9), 0) for k, c in prof.items()}
        return WhatIf(save_rate=save_rate, cost_per_call=cost_per_call, best_share=best[0], best_members_called=int(n * best[0]),
                      best_monthly_profit=round(best[1], 0), profit_at_10pct=at10)
