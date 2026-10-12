"""LLM providers behind one interface, each call metered for cost and latency (ADR-006, rule R13)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol

from src.services.contracts import Meter


@dataclass
class Completion:
    text: str
    meter: Meter


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, facts: dict) -> Completion: ...


def template_text(facts: dict) -> str:
    """Deterministic note built only from the facts. Always passes the grader; used as the fallback."""
    rs = facts["agent_reasons"]
    parts = [f"{r['label']} ({r['value']})" for r in rs[:3]]
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return (f"{facts['risk_level'].capitalize()} risk: {facts['probability_pct']}% chance of not renewing after expiry on "
            f"{facts['expiry']}. Main reasons: {joined}. Suggested action: {facts['action']}.")


@dataclass
class TemplateProvider:
    name: str = "template"
    model: str = "template-v1"

    def complete(self, system: str, user: str, facts: dict) -> Completion:
        t0 = time.perf_counter()
        text = template_text(facts)
        return Completion(text, Meter(provider=self.name, model=self.model, latency_ms=round((time.perf_counter() - t0) * 1000, 3)))


@dataclass
class OpenAIProvider:
    model: str
    price_in: float          # USD per 1M input tokens
    price_cached_in: float
    price_out: float
    max_output_tokens: int = 160
    temperature: float = 0.2
    timeout: float = 8.0
    client: object | None = None
    name: str = "openai"
    _ready: bool = field(default=False, repr=False)

    def _client(self):
        if self.client is None:
            from openai import OpenAI
            self.client = OpenAI(timeout=self.timeout)
        return self.client

    def cost(self, input_tokens: int, cached: int, output_tokens: int) -> float:
        return ((input_tokens - cached) * self.price_in + cached * self.price_cached_in + output_tokens * self.price_out) / 1e6

    def complete(self, system: str, user: str, facts: dict) -> Completion:
        t0 = time.perf_counter()
        r = self._client().responses.create(model=self.model, instructions=system, input=user,
                                            max_output_tokens=self.max_output_tokens, temperature=self.temperature)
        latency = (time.perf_counter() - t0) * 1000
        u = getattr(r, "usage", None)
        it = int(getattr(u, "input_tokens", 0) or 0)
        ot = int(getattr(u, "output_tokens", 0) or 0)
        details = getattr(u, "input_tokens_details", None)
        ct = int(getattr(details, "cached_tokens", 0) or 0)
        text = (getattr(r, "output_text", "") or "").strip()
        return Completion(text, Meter(provider=self.name, model=self.model, input_tokens=it, cached_input_tokens=ct,
                                      output_tokens=ot, latency_ms=round(latency, 1), cost_usd=round(self.cost(it, ct, ot), 8)))


def get_provider(llm_cfg: dict, prefer: str | None = None) -> Provider:
    """OpenAI only when a key is present (or explicitly requested); otherwise the free template provider."""
    want = prefer or llm_cfg.get("provider", "openai")
    if want == "openai" and os.environ.get("OPENAI_API_KEY"):
        return OpenAIProvider(model=llm_cfg["model"], price_in=llm_cfg["price_input_per_m"], price_cached_in=llm_cfg["price_cached_input_per_m"],
                              price_out=llm_cfg["price_output_per_m"], max_output_tokens=llm_cfg.get("max_output_tokens", 160),
                              temperature=llm_cfg.get("temperature", 0.2), timeout=llm_cfg.get("timeout_seconds", 8))
    return TemplateProvider()
