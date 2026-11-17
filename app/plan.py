"""Pure logic for the Streamlit companion app (R26): reads the committed public snapshot only, no model, no keys.

Profit follows the public API (ADR-010): save rate × value at risk − calls × cost per call. The app adds one input the API
does not have, a retention offer per saved member, so offer cost = offer × save rate × expected churners reached.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "deploy" / "public_snapshot.json"
BRIEF = ROOT / "docs" / "brief.yaml"
REPO = "https://github.com/sabrinapribadi/subscription-churn-at-scale"
API = "https://subscription-churn-at-scale.vercel.app"
PAGES = "https://sabrinapribadi.github.io/subscription-churn-at-scale/"


def load(path: Path = SNAPSHOT) -> dict:
    return json.loads(Path(path).read_text())


def _row(grid: dict, i: int, save_rate: float, cost: float, offer: float) -> dict:
    k, churners, ev = grid["k"][i], grid["expected_churners"][i], grid["expected_value_at_risk"][i]
    saved = save_rate * churners
    return {"share": (i + 1) / len(grid["k"]), "members_called": k, "expected_churners": churners, "expected_value_at_risk": ev,
            "expected_saved": saved, "expected_profit": round(save_rate * ev - cost * k - offer * saved, 0)}


def money(p: dict, save_rate: float, cost: float, offer: float = 0.0) -> list[dict]:
    """Where the expected profit comes from: value kept, minus call cost, minus offer cost (sums to p["expected_profit"])."""
    kept = save_rate * p["expected_value_at_risk"]
    return [{"step": "Value kept", "amount": kept}, {"step": "Call cost", "amount": -cost * p["members_called"]},
            {"step": "Offer cost", "amount": -offer * p["expected_saved"]}, {"step": "Expected profit", "amount": p["expected_profit"]}]


def plan(grid: dict, calls: int, save_rate: float, cost: float, offer: float = 0.0) -> dict:
    """Totals for calling the top `calls` members, at the nearest 0.1% of the cohort (the snapshot's grid, as the API does)."""
    n = len(grid["k"])
    i = min(n, max(1, round(calls / grid["members"] * n))) - 1
    return _row(grid, i, save_rate, cost, offer)


def curve(grid: dict, save_rate: float, cost: float, offer: float = 0.0, upto: float = 0.6, every: int = 5) -> list[dict]:
    """Expected profit every 0.5% of members up to `upto` (forecast)."""
    n = len(grid["k"])
    return [_row(grid, i, save_rate, cost, offer) for i in range(every - 1, int(n * upto), every)]


def best(rows: list[dict]) -> dict:
    return max(rows, key=lambda r: r["expected_profit"])


def backtest_best(scenarios: dict, save_rate: float, cost: float) -> dict:
    """Best share for value ranking on March 2017 members who actually churned (P4 curves; no offer cost: they hold value only)."""
    n, c = scenarios["members"], scenarios["value_curves"]["expected_value"]
    f, v = max(((f, save_rate * v - cost * n * f) for f, v in c), key=lambda q: q[1])
    return {"share": f, "members_called": int(n * f), "profit": round(v, 0)}


def demo_rows(snap: dict, call_share: float) -> list[dict]:
    """One row per synthetic demo member; `in_call_list` = ranked inside the top `call_share` of the real cohort."""
    out = []
    for mid, d in sorted(snap["demo"].items()):
        s = d["score"]
        out.append({"member": mid, "churn_chance": s["churn_probability"], "risk": s["risk_level"], "value_ntd": round(s["member_value"]),
                    "value_at_risk_ntd": round(s["expected_value_at_risk"]), "priority_percentile": s["priority_percentile"],
                    "in_call_list": s["priority_percentile"] >= 100 * (1 - call_share)})
    return out


def brief(path: Path = BRIEF) -> list[tuple[str, list[str]]]:
    """R22 brief items; links to repo files become absolute GitHub links (the app is not served from the repo)."""
    b = yaml.safe_load(Path(path).read_text())

    def fix(t: str) -> str:
        return re.sub(r"\]\((?!https?://)([^)]+)\)", lambda m: f"]({REPO}/blob/main/{m.group(1)})", t)

    return [(item["w"], [fix(str(x)) for x in item["lines"]]) for item in b["brief"]]
