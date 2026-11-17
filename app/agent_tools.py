"""Churn project's agent for the app chat: the repo's retention planner (ADR-007), its tools calling the public demo API.

SYSTEM and the tool schemas are copies of src/genai/agent.py and src/genai/tools.py; tests/test_streamlit_app.py fails if they drift.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("CHURN_API_BASE", "https://subscription-churn-at-scale.vercel.app")
MODEL = "gpt-6-luna"                                                      # configs/default_config.yaml, agent.model
PRICES = {"input": 0.10, "cached_input": 0.01, "output": 0.50}            # USD per 1M tokens (read 2026-10-12)
SCHEMAS = json.loads((Path(__file__).resolve().parent / "agent_schemas.json").read_text())
SYSTEM = "You are a retention planning assistant for a music subscription service.\nAnswer questions about members' risk of not renewing, why they are at risk, who to call, and what calling costs and earns.\nAlways use the tools for facts; never guess a number. Every number in your answer must come from the question or a tool result:\nquote tool numbers (rounding is fine) and do not calculate new ones such as differences or totals.\nShares are fractions in the tools (0.05 = 5% of members). Money is in the dataset's units, without a currency sign.\nUse the defaults only when the question gives no save rate or cost per call, and say which assumptions you used.\nNever mention age, gender or city. If a question is outside these topics, say what you can help with instead, without calling tools.\nAnswer in at most 120 words, plain English, no tables."


def _get(path: str, params: dict | None = None) -> dict:
    url = API.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "churn-streamlit-agent/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": "unknown member: only demo members demo-001 to demo-100 are served (real members are not published)"}
        raise


def _id(m: str) -> str:
    return urllib.parse.quote(str(m), safe="")


def _why(member_id: str) -> dict:
    """Same fields as the repo's why_at_risk tool."""
    e = _get(f"/members/{_id(member_id)}/explanation")
    if "error" in e:
        return e
    return {"member_id": e["member_id"], "note": e["narrative"], "suggested_action": e["suggested_action"],
            "reasons": [r for r in e["reasons"] if r.get("shown_to_agent", True)], "grounded": e.get("grounded")}


FNS = {
    "member_risk": lambda member_id: _get(f"/members/{_id(member_id)}/score"),
    "why_at_risk": lambda member_id: _why(member_id),
    "call_list": lambda share=0.10, limit=5, save_rate=0.20, cost_per_call=20.0: _get(
        "/call-list", {"share": share, "limit": limit, "save_rate": save_rate, "cost_per_call": cost_per_call}),
    "what_if": lambda save_rate=0.20, cost_per_call=20.0: _get("/what-if", {"save_rate": save_rate, "cost_per_call": cost_per_call}),
}
TOOLS = {s["name"]: {"schema": s, "fn": FNS[s["name"]]} for s in SCHEMAS}

QUESTIONS = [                                                             # recorded for replay by scripts/record_agent_replays.py
    "How many members should we call if we keep 1 in 4 churners we reach and a call costs 15?",
    "What profit do we make if we call the top 5% of members at a 20% save rate and 20 per call?",
    "Compare calling 5% and 10% of members at the default assumptions.",
    "If only 1 in 10 called churners stay and each call costs 30, is a campaign still worth it?",
    "Why is demo-001 at risk, and what should the agent say?",
    "How risky is demo-042 and where do they rank on the call list?",
    "Who should we call first?",
    "What is the churn risk of member Wk8vF3qZ+abc=?",
    "What will the weather be in Taipei tomorrow?",
]
