"""One tool registry for AI agents (ADR-006): served by the MCP gateway and exportable as OpenAI function schemas."""

from __future__ import annotations

import inspect
from typing import Callable

from pydantic import create_model


def build_tools(client) -> list[Callable]:
    """Typed tools bound to a service client (LocalClient or HttpClient)."""

    def member_risk(member_id: str) -> dict:
        """How likely this member is to leave after their next expiry, what they are worth, and where they rank on the call list."""
        return client.score(member_id).model_dump()

    def why_at_risk(member_id: str) -> dict:
        """Plain-language reasons this member is at risk, the evidence behind them, and one suggested action."""
        e = client.explanation(member_id)
        return {"member_id": e.member_id, "note": e.narrative, "suggested_action": e.suggested_action,
                "reasons": [r.model_dump() for r in e.reasons if r.shown_to_agent], "grounded": e.grounded,
                "cost_usd": e.meter.cost_usd, "latency_ms": e.meter.latency_ms}

    def call_list(share: float = 0.10, limit: int = 20, save_rate: float = 0.20, cost_per_call: float = 20.0) -> dict:
        """Who to call first: the top members by expected value at risk, plus expected churners, value and profit for the whole call list."""
        return client.call_list(share=share, limit=limit, save_rate=save_rate, cost_per_call=cost_per_call).model_dump()

    def what_if(save_rate: float = 0.20, cost_per_call: float = 20.0) -> dict:
        """For an assumed save rate and cost per call: the best share of members to call and the monthly profit (from March 2017 results)."""
        return client.what_if(save_rate=save_rate, cost_per_call=cost_per_call).model_dump()

    return [member_risk, why_at_risk, call_list, what_if]


def openai_tool_schemas(tools: list[Callable]) -> list[dict]:
    """Same tools as OpenAI function-calling definitions, derived from the Python signatures."""
    out = []
    for fn in tools:
        fields = {n: (p.annotation, ... if p.default is inspect.Parameter.empty else p.default)
                  for n, p in inspect.signature(fn).parameters.items()}
        schema = create_model(fn.__name__, **fields).model_json_schema()
        schema.pop("title", None)
        out.append({"type": "function", "name": fn.__name__, "description": inspect.getdoc(fn), "parameters": schema})
    return out
