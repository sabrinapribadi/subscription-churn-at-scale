"""One tool registry for AI agents (ADR-006): served by the MCP gateway and exportable as OpenAI function schemas."""

from __future__ import annotations

import inspect
from typing import Annotated, Callable

from pydantic import Field, create_model

MAX_LISTED = 50  # members returned per call; the summary always covers the whole share

Share = Annotated[float, Field(gt=0, le=1, description="Fraction of all members to call, e.g. 0.05 for 5%")]
SaveRate = Annotated[float, Field(ge=0, le=1, description="Share of called churners who stay, e.g. 0.2 for 1 in 5")]
Cost = Annotated[float, Field(ge=0, description="Cost of one call, in the dataset's money units")]


def build_tools(client) -> list[Callable]:
    """Typed tools bound to a service client (LocalClient or HttpClient)."""

    def member_risk(member_id: Annotated[str, Field(description="Member id")]) -> dict:
        """How likely this member is to leave after their next expiry, what they are worth, and where they rank on the call list."""
        return client.score(member_id).model_dump()

    def why_at_risk(member_id: Annotated[str, Field(description="Member id")]) -> dict:
        """Plain-language reasons this member is at risk, the evidence behind them, and one suggested action."""
        e = client.explanation(member_id)
        return {"member_id": e.member_id, "note": e.narrative, "suggested_action": e.suggested_action,
                "reasons": [r.model_dump() for r in e.reasons if r.shown_to_agent], "grounded": e.grounded,
                "cost_usd": e.meter.cost_usd, "latency_ms": e.meter.latency_ms}

    def call_list(share: Share = 0.10,
                  limit: Annotated[int, Field(ge=1, le=MAX_LISTED, description="How many of the first members to list")] = 5,
                  save_rate: SaveRate = 0.20, cost_per_call: Cost = 20.0) -> dict:
        """Calling a given share of members: expected churners, value at risk and expected profit for that whole share,
        plus the first members to call. Use this for "what profit if we call X%" and "who do we call first"."""
        return client.call_list(share=share, limit=min(limit, MAX_LISTED), save_rate=save_rate, cost_per_call=cost_per_call).model_dump()

    def what_if(save_rate: SaveRate = 0.20, cost_per_call: Cost = 20.0) -> dict:
        """Finds the BEST share of members to call for a save rate and cost per call, and the monthly profit at that best share
        (from March 2017 results). Use call_list instead for the profit of a specific share."""
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
