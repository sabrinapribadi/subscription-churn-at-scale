"""Retention planner agent (ADR-007): loop, tool errors, grounding guard, endpoint. Scripted LLM, no API key."""

import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from src.genai.agent import RetentionPlanner, fallback_answer, ungrounded_numbers
from src.genai.explain import Explainer
from src.services.apps import explain_app
from src.services.contracts import PlannerAnswer, ToolCall

USAGE = NS(input_tokens=500, output_tokens=60, input_tokens_details=NS(cached_tokens=0))


def call(name, **args):
    return NS(type="function_call", name=name, arguments=json.dumps(args), call_id=f"c_{name}")


class ScriptedLLM:
    """Plays back one turn per round; a callable turn gets the tool outputs so far and returns text."""

    def __init__(self, turns):
        self.turns, self.requests = list(turns), []
        self.responses = NS(create=self._create)

    def _create(self, **kw):
        self.requests.append(kw)
        turn = self.turns.pop(0)
        if callable(turn):
            outs = [json.loads(i["output"]) for i in kw["input"] if isinstance(i, dict) and i.get("type") == "function_call_output"]
            turn = turn(outs)
        if isinstance(turn, str):
            return NS(output=[NS(type="message")], output_text=turn, usage=USAGE)
        return NS(output=turn, output_text="", usage=USAGE)


def planner(client, turns, max_steps=4):
    return RetentionPlanner(client=client, model="m", price_in=0.10, price_cached_in=0.01, price_out=0.50,
                            max_steps=max_steps, llm=ScriptedLLM(turns))


def test_tool_then_grounded_answer(client):
    def answer(outs):
        w = outs[-1]
        return (f"At a 20% save rate and 20 per call, call {100 * w['best_share']:.1f}% of members "
                f"({w['best_members_called']:,}) for a monthly profit of {w['best_monthly_profit']:,.0f}.")
    p = planner(client, [[call("what_if", save_rate=0.2, cost_per_call=20)], answer])
    a = p.ask("What share should we call at a 20% save rate and 20 per call?")
    assert a.grounded and not a.grounded_fallback and a.steps == 2
    assert [c.name for c in a.tool_calls] == ["what_if"] and a.tool_calls[0].arguments == {"save_rate": 0.2, "cost_per_call": 20}
    assert a.meter.input_tokens == 1000 and a.meter.cost_usd == pytest.approx((1000 * 0.10 + 120 * 0.50) / 1e6)


def test_invented_number_falls_back_to_tool_answer(client):
    p = planner(client, [[call("what_if", save_rate=0.2, cost_per_call=20)], "Call 7.3% of members for a profit of 999,999."])
    a = p.ask("What share should we call?")
    assert not a.grounded and a.grounded_fallback and not a.checks["numbers_grounded"]
    assert a.answer.startswith("At a 20.0% save rate and 20 per call") and not ungrounded_numbers(a.answer, [a.question, [client.what_if(0.2, 20).model_dump()]])


def test_chained_tools_call_list_then_reasons(client, store):
    first = store.order[0]
    p = planner(client, [[call("call_list", share=0.05, limit=3, save_rate=0.2, cost_per_call=20)],
                         [call("why_at_risk", member_id=first)],
                         lambda outs: f"Member {first} is first on the list. {outs[-1]['note']}"])
    a = p.ask("Who is first on the call list, and why?")
    assert [c.name for c in a.tool_calls] == ["call_list", "why_at_risk"] and a.grounded, a.checks


def test_unknown_member_error_goes_back_to_the_model(client):
    p = planner(client, [[call("member_risk", member_id="nope")], "I could not find member nope; please check the id."])
    a = p.ask("How risky is member nope?")
    assert a.tool_calls == [ToolCall(name="member_risk", arguments={"member_id": "nope"}, ok=False)] and a.grounded


def test_out_of_scope_needs_no_tools(client):
    a = planner(client, ["I can help with churn risk, reasons, call lists and call budgets."]).ask("What's the weather tomorrow?")
    assert a.tool_calls == [] and a.grounded and a.steps == 1


def test_last_round_forces_an_answer(client):
    loop = [[call("what_if", save_rate=0.2, cost_per_call=20)]] * 2 + ["Done."]
    p = planner(client, loop, max_steps=3)
    a = p.ask("Keep checking what-if.")
    assert a.steps == 3 and p.llm.requests[-1]["tool_choice"] == "none" and p.llm.requests[0]["tool_choice"] == "auto"


def test_sensitive_words_only_allowed_if_the_question_used_them(client, store):
    m = store.order[0]
    ok = planner(client, [[call("why_at_risk", member_id=m)], "No: age and gender are never used in agent notes."]).ask(
        f"Is member {m} at risk because of their age or gender?")
    bad = planner(client, [[call("member_risk", member_id=m)], "This member is a young female."]).ask(f"How risky is member {m}?")
    assert ok.checks["no_sensitive_attributes"] and not bad.checks["no_sensitive_attributes"] and bad.grounded_fallback


def test_grounding_handles_rounding_units_and_dates():
    src = [{"best_share": 0.215, "best_monthly_profit": 13_912_345.0, "expiry_date": 20170315, "members": 862158}]
    assert ungrounded_numbers("Call 21.5% (≈13.9M a month) before 2017-03-15; 862,158 members.", src) == []
    assert ungrounded_numbers("Profit 14.2M.", src) == ["14.2M"]


def test_fallback_without_tools_explains_scope():
    assert "help with" in fallback_answer([], [])
    assert "unknown member x" in fallback_answer([ToolCall(name="member_risk", arguments={}, ok=False)], [{"error": "unknown member x"}])


def test_ask_endpoint(client, store):
    plain = TestClient(explain_app(client, Explainer()))
    assert plain.post("/ask", json={"question": "Who should we call?"}).status_code == 503
    p = planner(client, [[call("what_if", save_rate=0.2, cost_per_call=20)], "Here is the plan."])
    app = TestClient(explain_app(client, Explainer(), p))
    body = app.post("/ask", json={"question": "Who should we call?"}).json()
    assert PlannerAnswer(**body).tool_calls[0].name == "what_if" and app.get("/health").json()["planner"] == "m"
    assert app.post("/ask", json={"question": ""}).status_code == 422


def test_negative_numbers_keep_their_sign():
    """Held-out run (ADR-009): a correct '-7,245,823' was rejected because the sign was dropped."""
    src = [{"summary": {"expected_profit": -7245823.0}}]
    assert ungrounded_numbers("Expected profit is -7,245,823, so calls lose money.", src) == []
    assert ungrounded_numbers("Expected profit is −7.2M.", src) == []
    assert ungrounded_numbers("Expected profit is 7,245,823.", src) == ["7,245,823"]
