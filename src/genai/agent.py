"""Retention planner: one tool-using agent over the shared tool registry (ADR-007, rule R13).

A manager asks a question in plain words; the agent picks tools (member_risk, why_at_risk,
call_list, what_if), reads their results and answers. Every number in the answer must come
from the question or a tool result (within rounding); otherwise a deterministic answer built
from the last tool result is returned instead. Each question is metered for cost and latency.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from src.genai.grader import _SENSITIVE_WORDS
from src.genai.tools import build_tools, openai_tool_schemas
from src.services.contracts import Meter, PlannerAnswer, ToolCall

SYSTEM = """You are a retention planning assistant for a music subscription service.
Answer questions about members' risk of not renewing, why they are at risk, who to call, and what calling costs and earns.
Always use the tools for facts; never guess a number. Every number in your answer must come from the question or a tool result:
quote tool numbers (rounding is fine) and do not calculate new ones such as differences or totals.
Shares are fractions in the tools (0.05 = 5% of members). Money is in the dataset's units, without a currency sign.
Use the defaults only when the question gives no save rate or cost per call, and say which assumptions you used.
Never mention age, gender or city. If a question is outside these topics, say what you can help with instead, without calling tools.
Answer in at most 120 words, plain English, no tables."""

MAX_WORDS = 120
OUT_OF_SCOPE = ("I can help with member churn risk, the reasons behind it, who to call first, and what calling costs and earns. "
                "Ask me about a member, a call list, or a save rate and cost per call.")
_NUM = re.compile(r"(?<![\w.])([-−]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|[kKmM]\b)?")  # sign kept: a loss is not a profit


# ------------------------------------------------------------------ grounding
def _leaves(x, out: list[float]) -> None:
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        out.append(float(x))
        if isinstance(x, int) and 19000101 <= x <= 21001231:  # yyyymmdd dates are written as 2017-03-15
            out += [x // 10000, x // 100 % 100, x % 100]
    elif isinstance(x, str):
        for m in _NUM.finditer(x):
            out.append(_value(m))
        for d in re.findall(r"\d{4}-\d{2}-\d{2}", x):
            out += [float(p) for p in d.split("-")]
    elif isinstance(x, dict):
        for v in x.values():
            _leaves(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _leaves(v, out)


def _value(m: re.Match) -> float:
    v = float(m.group(2).replace(",", "") + (f".{m.group(3)}" if m.group(3) else ""))
    return -v if m.group(1) else v


def answer_numbers(text: str) -> list[tuple[str, float, float]]:
    """(as written, value, rounding tolerance) for each number in the answer; 12.5M -> 12,500,000 ± 50,000."""
    out = []
    for m in _NUM.finditer(text):
        dec, unit = m.group(3) or "", (m.group(4) or "").lower()
        v = _value(m)
        tol = 0.5 * 10 ** -len(dec)
        scale = {"k": 1e3, "m": 1e6}.get(unit, 1.0)
        out.append((m.group(0).strip(), v * scale, tol * scale))
    return out


def ungrounded_numbers(text: str, sources: list) -> list[str]:
    vals: list[float] = []
    _leaves(sources, vals)
    pool = vals + [v * 100 for v in vals if abs(v) <= 1.0] + [v / 100 for v in vals]  # 0.05 may be written as 5%
    bad = []
    for raw, v, tol in answer_numbers(text):
        if v <= 10 and float(v).is_integer():  # small counts and list positions ("top 3", "1.")
            continue
        if not any(abs(v - s) <= max(tol, 1e-9) or (s and abs(v - s) / abs(s) <= 0.005) for s in pool):
            bad.append(raw)
    return bad


def grade_answer(text: str, question: str, tool_results: list) -> dict[str, bool]:
    allowed_words = {w.lower() for w in _SENSITIVE_WORDS.findall(question)}
    sensitive = [w for w in _SENSITIVE_WORDS.findall(text) if w.lower() not in allowed_words]
    return {"numbers_grounded": not ungrounded_numbers(text, [question, tool_results]),
            "no_sensitive_attributes": not sensitive,
            "length_ok": len(text.split()) <= MAX_WORDS,
            "not_empty": bool(text.strip())}


# ------------------------------------------------------------------ fallback
def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def fallback_answer(calls: list[ToolCall], results: list) -> str:
    """Deterministic answer from the last successful tool result; always grounded."""
    for c, r in zip(reversed(calls), reversed(results)):
        if not isinstance(r, dict) or "error" in r:
            continue
        if c.name == "member_risk":
            return (f"Member {r['member_id']}: {r['risk_level']} risk, {_pct(r['churn_probability'])} chance of not renewing; "
                    f"value {r['member_value']:,.0f} over 12 months; number {r['priority_rank']:,} on the call list.")
        if c.name == "why_at_risk":
            return r["note"]
        if c.name == "call_list":
            s, q = r["summary"], r["request"]
            first = ", ".join(m["member_id"] for m in r["members"][:3])
            return (f"Calling the top {s['members_called']:,} members ({_pct(q['share'])}) at a {_pct(q['save_rate'])} save rate and "
                    f"{q['cost_per_call']:,.0f} per call: about {s['expected_churners']:,.0f} expected churners, "
                    f"{s['expected_value_at_risk']:,.0f} value at risk, expected profit {s['expected_profit']:,.0f}. First to call: {first}.")
        if c.name == "what_if":
            return (f"At a {_pct(r['save_rate'])} save rate and {r['cost_per_call']:,.0f} per call, the best share to call is "
                    f"{_pct(r['best_share'])} ({r['best_members_called']:,} members), for a monthly profit of {r['best_monthly_profit']:,.0f}.")
    if calls:
        return "I could not get that from the tools: " + "; ".join(str(r.get("error")) for r in results if isinstance(r, dict) and "error" in r)
    return OUT_OF_SCOPE


# ------------------------------------------------------------------ agent
@dataclass
class RetentionPlanner:
    client: object                   # service client (LocalClient or HttpClient)
    model: str
    price_in: float
    price_cached_in: float
    price_out: float
    reasoning_effort: str | None = None
    max_steps: int = 4               # LLM rounds, tool calls included
    max_output_tokens: int = 400
    timeout: float = 20.0
    llm: object | None = None        # OpenAI client; injected in tests
    tools: dict = field(init=False)
    schemas: list = field(init=False)

    def __post_init__(self):
        fns = build_tools(self.client)
        self.tools = {f.__name__: f for f in fns}
        self.schemas = openai_tool_schemas(fns)

    def _llm(self):
        if self.llm is None:
            from openai import OpenAI
            self.llm = OpenAI(timeout=self.timeout)
        return self.llm

    def _run_tool(self, name: str, arguments: str) -> tuple[dict, object]:
        """Run one tool call; errors go back to the model as data so it can correct itself."""
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {}, {"error": "arguments were not valid JSON"}
        if name not in self.tools:
            return args, {"error": f"unknown tool {name}"}
        try:
            return args, self.tools[name](**args)
        except KeyError as e:
            return args, {"error": f"unknown member {e.args[0] if e.args else ''}".strip()}
        except Exception as e:  # bad arguments from the model
            return args, {"error": f"{type(e).__name__}: {str(e)[:200]}"}

    def ask(self, question: str) -> PlannerAnswer:
        t0 = time.perf_counter()
        items: list = [{"role": "user", "content": question}]
        calls: list[ToolCall] = []
        results: list = []
        it = ct = ot = 0
        text, steps = "", 0
        extra = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        for steps in range(1, self.max_steps + 1):
            final_round = steps == self.max_steps
            r = self._llm().responses.create(model=self.model, instructions=SYSTEM, input=items, max_output_tokens=self.max_output_tokens,
                                             tools=self.schemas, tool_choice="none" if final_round else "auto", **extra)
            u = getattr(r, "usage", None)
            it += int(getattr(u, "input_tokens", 0) or 0)
            ot += int(getattr(u, "output_tokens", 0) or 0)
            ct += int(getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0)
            fcalls = [o for o in (getattr(r, "output", None) or []) if getattr(o, "type", "") == "function_call"]
            if not fcalls:
                text = (getattr(r, "output_text", "") or "").strip()
                break
            items += list(r.output)
            for fc in fcalls:
                args, res = self._run_tool(fc.name, fc.arguments)
                calls.append(ToolCall(name=fc.name, arguments=args, ok=not (isinstance(res, dict) and "error" in res)))
                results.append(res)
                items.append({"type": "function_call_output", "call_id": fc.call_id, "output": json.dumps(res, default=str)})
        checks = grade_answer(text, question, results)
        grounded = all(checks.values())
        answer = text if grounded else fallback_answer(calls, results)
        cost = ((it - ct) * self.price_in + ct * self.price_cached_in + ot * self.price_out) / 1e6
        cost += sum(r.get("cost_usd", 0.0) for c, r in zip(calls, results) if c.name == "why_at_risk" and isinstance(r, dict))  # nested note writer
        meter = Meter(provider="openai", model=self.model, input_tokens=it, cached_input_tokens=ct, output_tokens=ot,
                      latency_ms=round((time.perf_counter() - t0) * 1000, 1), cost_usd=round(cost, 8))
        return PlannerAnswer(question=question, answer=answer, grounded=grounded, grounded_fallback=not grounded, checks=checks,
                             tool_calls=calls, steps=steps, meter=meter)


def get_planner(client, cfg: dict, llm=None) -> RetentionPlanner:
    a, p = cfg["agent"], cfg["llm"]
    return RetentionPlanner(client=client, model=a.get("model", p["model"]), price_in=p["price_input_per_m"],
                            price_cached_in=p["price_cached_input_per_m"], price_out=p["price_output_per_m"],
                            reasoning_effort=a.get("reasoning_effort"), max_steps=a.get("max_steps", 4),
                            max_output_tokens=a.get("max_output_tokens", 400), timeout=a.get("timeout_seconds", 20), llm=llm)

