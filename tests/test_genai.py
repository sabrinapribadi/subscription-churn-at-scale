"""GenAI module: grader, providers (metered), guard, cache, latency budget (ADR-006, rule R13)."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from src.genai.explain import Explainer, build_facts
from src.genai.grader import grade
from src.genai.providers import OpenAIProvider, TemplateProvider, get_provider, template_text
from src.genai.tools import build_tools, openai_tool_schemas
from src.services.contracts import Reason, Reasons, Score

CFG = yaml.safe_load(Path("configs/default_config.yaml").read_text())
CASES = json.loads(Path("tests/llm_eval/cases.json").read_text())


def case_inputs(c):
    s = Score(member_id=c["id"], churn_probability=c["p"], risk_level=c["risk"], member_value=c["value"],
              expected_value_at_risk=c["p"] * c["value"], priority_rank=1, priority_percentile=100, expiry_date=c["expiry"], model_version="t")
    rs = Reasons(member_id=c["id"], model_version="t", reasons=[Reason(**r) for r in c["reasons"]])
    return s, rs


class FakeOpenAI:
    """Stands in for the OpenAI client: returns a scripted text and token usage."""
    def __init__(self, text, usage=(420, 0, 95)):
        it, ct, ot = usage
        self.responses = SimpleNamespace(create=lambda **kw: SimpleNamespace(
            output_text=text, usage=SimpleNamespace(input_tokens=it, output_tokens=ot, input_tokens_details=SimpleNamespace(cached_tokens=ct))))


def provider(text, usage=(420, 0, 95)):
    L = CFG["llm"]
    return OpenAIProvider(model=L["model"], price_in=L["price_input_per_m"], price_cached_in=L["price_cached_input_per_m"],
                          price_out=L["price_output_per_m"], client=FakeOpenAI(text, usage))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_set_template_is_grounded(case):
    s, rs = case_inputs(case)
    e = Explainer(TemplateProvider()).explain(s, rs)
    assert e.grounded and not e.grounded_fallback, e.checks
    assert e.suggested_action == case["expected_action"]
    assert not any(w in e.narrative.lower() for w in case.get("must_not_mention", []))


def test_grader_catches_invented_numbers_features_and_bad_endings():
    s, rs = case_inputs(CASES[0]); f = build_facts(s, rs); ok = template_text(f)
    assert all(grade(ok, f).values())
    assert not grade(ok.replace(f"{f['probability_pct']}%", "99%"), f)["numbers_grounded"]
    assert not grade(ok + " Also their songs skipped early is high.", f)["no_other_features"] or not grade(ok + " Also their songs skipped early is high.", f)["action_ok"]
    assert not grade(ok.replace("Suggested action", "Maybe"), f)["action_ok"]
    assert not grade("She is a 34 year old woman. " + ok, f)["no_sensitive_attributes"]
    assert not grade(" ".join(["word"] * 100) + ok, f)["length_ok"]


def test_openai_text_that_invents_facts_falls_back_to_template():
    s, rs = case_inputs(CASES[0])
    e = Explainer(provider("This member will certainly leave because of a 50% price rise. Suggested action: call now.")).explain(s, rs)
    assert e.grounded and e.grounded_fallback and e.narrative == template_text(build_facts(s, rs))


def test_openai_grounded_text_is_used_and_metered():
    s, rs = case_inputs(CASES[0]); text = template_text(build_facts(s, rs))
    e = Explainer(provider(text, usage=(420, 100, 95))).explain(s, rs)
    assert not e.grounded_fallback and e.meter.provider == "openai" and e.meter.input_tokens == 420
    L = CFG["llm"]
    expected = (320 * L["price_input_per_m"] + 100 * L["price_cached_input_per_m"] + 95 * L["price_output_per_m"]) / 1e6
    assert e.meter.cost_usd == pytest.approx(expected)
    assert expected * 1000 <= L["budget_cost_per_1000"]  # R13 cost budget at a typical token count


def test_cache_hit_costs_nothing():
    s, rs = case_inputs(CASES[0]); text = template_text(build_facts(s, rs))
    ex = Explainer(provider(text))
    first, second = ex.explain(s, rs), ex.explain(s, rs)
    assert first.meter.cost_usd > 0 and second.meter.cache_hit and second.meter.cost_usd == 0


def test_template_and_cached_paths_meet_latency_budget(client, store):
    budget = CFG["llm"]["budget_p95_ms_cached"]
    for label in ("template", "cached"):
        lat = []
        for m in store.order[:200]:
            t = time.perf_counter(); client.explanation(m); lat.append((time.perf_counter() - t) * 1000)
        assert np.percentile(lat, 95) <= budget, (label, np.percentile(lat, 95))


def test_without_key_the_free_provider_is_used(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert isinstance(get_provider(CFG["llm"]), TemplateProvider)


def test_one_tool_registry_for_mcp_and_openai(client):
    tools = build_tools(client)
    schemas = {t["name"]: t for t in openai_tool_schemas(tools)}
    assert set(schemas) == {"member_risk", "why_at_risk", "call_list", "what_if"}
    assert schemas["member_risk"]["parameters"]["required"] == ["member_id"]
    assert "required" not in schemas["what_if"]["parameters"]
