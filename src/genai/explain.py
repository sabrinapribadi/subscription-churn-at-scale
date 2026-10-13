"""Explainer: facts → prompt → provider → grader → guard, with a cache (ADR-006, rule R13)."""

from __future__ import annotations

import time
from collections import OrderedDict

from src.genai.grader import ACTIONS, grade
from src.genai.providers import Provider, TemplateProvider, template_text
from src.genai.registry import load_prompt
from src.services.contracts import Explanation, Meter, Reasons, Score


def choose_action(score: Score, reasons: Reasons) -> str:
    feats = {r.feature: r for r in reasons.reasons}
    if score.risk_level == "low":
        return "no call needed"
    if "last_auto_renew" in feats and feats["last_auto_renew"].value == "off":
        return "help switch to auto-renew"
    if any(f in feats and feats[f].direction == "raises risk" for f in ("days_since_last_play", "use_decline_ratio", "use_active_days_recent")):
        return "send a re-engagement message"
    if score.risk_level == "high":
        return "offer a discount on the next plan"
    return "send a renewal reminder"


def build_facts(score: Score, reasons: Reasons) -> dict:
    agent = [r.model_dump() for r in reasons.reasons if r.shown_to_agent][:3]
    action = choose_action(score, reasons)
    assert action in ACTIONS
    pct = int(round(score.churn_probability * 100))
    e = str(score.expiry_date)
    expiry = f"{e[:4]}-{e[4:6]}-{e[6:]}"
    value = f"{int(round(score.member_value))}"
    reasons_block = "\n".join(f"- {r['label']}: {r['value']} ({r['direction']})" for r in agent)
    return {"risk_level": score.risk_level, "probability_pct": pct, "expiry": expiry, "value": value, "action": action,
            "agent_reasons": agent, "reasons_block": reasons_block,
            "allowed_number_sources": [pct, expiry, value, 12, *[r["value"] for r in agent], *[r["label"] for r in agent]]}


class Explainer:
    def __init__(self, provider: Provider | None = None, prompt: str = "explain_member", version: str = "v2", cache_size: int = 100_000):
        self.provider = provider or TemplateProvider()
        self.prompt = load_prompt(prompt, version)
        self.cache: OrderedDict[tuple, Explanation] = OrderedDict()
        self.cache_size = cache_size

    def key(self, score: Score) -> tuple:
        return (score.member_id, score.model_version, self.prompt.version, self.provider.name, self.provider.model)

    def cached(self, score: Score) -> Explanation | None:
        """Check the cache before any expensive work (reasons, LLM): a repeat question costs nothing (R13)."""
        t0 = time.perf_counter()
        k = self.key(score)
        if k not in self.cache:
            return None
        hit = self.cache[k]; self.cache.move_to_end(k)
        meter = Meter(provider=hit.meter.provider, model=hit.meter.model, latency_ms=round((time.perf_counter() - t0) * 1000, 3), cache_hit=True)
        return hit.model_copy(update={"meter": meter})

    def explain(self, score: Score, reasons: Reasons) -> Explanation:
        hit = self.cached(score)
        if hit is not None:
            return hit
        k = self.key(score)
        facts = build_facts(score, reasons)
        system, user = self.prompt.render(facts)
        try:
            out = self.provider.complete(system, user, facts)
            text, meter = out.text, out.meter
        except Exception:
            text, meter = "", Meter(provider=self.provider.name, model=self.provider.model)
        checks = grade(text, facts) if text else {"provider_error": False}
        fallback = not all(checks.values())
        if fallback:
            text = template_text(facts)
            checks = grade(text, facts)
        exp = Explanation(member_id=score.member_id, score=score, reasons=reasons.reasons, narrative=text, suggested_action=facts["action"],
                          prompt_version=f"{self.prompt.name}.{self.prompt.version}", grounded=all(checks.values()),
                          grounded_fallback=fallback, checks=checks, meter=meter)
        self.cache[k] = exp
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return exp
