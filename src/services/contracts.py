"""Typed contracts shared by every service, client and tool (ADR-005). Field names are pinned by contract tests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    service: str
    status: Literal["ok"] = "ok"
    model_version: str
    members: int


class MemberFeatures(BaseModel):
    member_id: str
    cohort: int
    snapshot_date: int = Field(description="yyyymmdd; features use only data before this date")
    expiry_date: int
    features: dict[str, float | None]


class Score(BaseModel):
    member_id: str
    churn_probability: float = Field(ge=0, le=1, description="calibrated (isotonic + prior shift)")
    risk_level: Literal["low", "medium", "high"]
    member_value: float = Field(ge=0, description="12 months of the current plan")
    expected_value_at_risk: float = Field(ge=0, description="churn_probability × member_value")
    priority_rank: int = Field(ge=1, description="1 = call first (ordered by expected value at risk)")
    priority_percentile: float = Field(ge=0, le=100)
    expiry_date: int
    model_version: str


class Reason(BaseModel):
    feature: str
    label: str
    value: str
    contribution: float = Field(description="log-odds contribution (TreeSHAP)")
    direction: Literal["raises risk", "lowers risk"]
    shown_to_agent: bool = Field(description="False for demographic features, which are never quoted to agents")


class Reasons(BaseModel):
    member_id: str
    reasons: list[Reason]
    model_version: str


class CallListRequest(BaseModel):
    share: float = Field(0.10, gt=0, le=1, description="share of the cohort to call")
    limit: int = Field(20, ge=1, le=500, description="how many members to return in this response")
    save_rate: float = Field(0.20, ge=0, le=1)
    cost_per_call: float = Field(20.0, ge=0)


class CallListSummary(BaseModel):
    members_called: int
    expected_churners: float
    expected_value_at_risk: float
    expected_profit: float = Field(description="save_rate × expected value at risk − cost of calls")


class CallList(BaseModel):
    request: CallListRequest
    summary: CallListSummary
    members: list[Score]


class Meter(BaseModel):
    provider: str
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cache_hit: bool = False


class Explanation(BaseModel):
    member_id: str
    score: Score
    reasons: list[Reason]
    narrative: str
    suggested_action: str
    prompt_version: str
    grounded: bool
    grounded_fallback: bool = Field(description="True if the provider text failed the grader and the template text was used")
    checks: dict[str, bool]
    meter: Meter


class WhatIf(BaseModel):
    save_rate: float
    cost_per_call: float
    best_share: float
    best_members_called: int
    best_monthly_profit: float
    profit_at_10pct: dict[str, float]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class ToolCall(BaseModel):
    name: str
    arguments: dict
    ok: bool


class PlannerAnswer(BaseModel):
    question: str
    answer: str
    grounded: bool
    grounded_fallback: bool = Field(description="True if the agent's text failed the grader and a tool-built answer was used")
    checks: dict[str, bool]
    tool_calls: list[ToolCall]
    steps: int = Field(description="LLM rounds used")
    meter: Meter
