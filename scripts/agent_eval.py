"""Live evaluation of the retention planner agent (ADR-007, rule R13).

    OPENAI_API_KEY=... python scripts/agent_eval.py [--repeats 3]

Runs each question in tests/llm_eval/planner_questions.json against real serving artefacts. A question
succeeds when the agent called the expected tools with the expected arguments, its own answer passed the
grader (before any fallback), and it mentioned nothing it must not. Reports success, tool accuracy, steps,
cost per 1,000 questions and latency against the budgets in configs/default_config.yaml.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.genai.agent import get_planner  # noqa: E402
from src.genai.explain import Explainer  # noqa: E402
from src.genai.grader import mentions_any  # noqa: E402
from src.genai.providers import get_provider  # noqa: E402
from src.services.clients import LocalClient  # noqa: E402
from src.services.store import ServingStore  # noqa: E402


def fill(x, ph: dict):
    if isinstance(x, str):
        if x.startswith("{") and x.endswith("}") and x[1:-1] in ph:
            return ph[x[1:-1]]
        return x.format(**ph) if "{" in x else x
    if isinstance(x, dict):
        return {k: fill(v, ph) for k, v in x.items()}
    if isinstance(x, list):
        return [fill(v, ph) for v in x]
    return x


def close(a, b) -> bool:
    if isinstance(b, (int, float)) and isinstance(a, (int, float)):
        return abs(a - b) <= max(1e-6, 0.03 * abs(b))
    return a == b


def matched(expect: dict, calls) -> bool:
    return any(c.name == expect["tool"] and all(k in c.arguments and close(c.arguments[k], v) for k, v in expect["args"].items())
               for c in calls)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--repeats", type=int, default=3); a = ap.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set; the planner needs a live LLM.")
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    store = ServingStore(os.path.expanduser(os.environ.get("SERVING_DIR", "~/data/kkbox/serving")))
    client = LocalClient(store, Explainer(get_provider(cfg["llm"])))  # notes written by the live LLM, as deployed
    planner = get_planner(client, cfg)
    ph = {"top_member": store.order[0], "mid_member": store.order[50_000], "low_member": store.order[-1],
          "best_share_20_20": store.what_if(0.2, 20).best_share}
    questions = fill(json.loads(Path("tests/llm_eval/planner_questions.json").read_text()), ph)
    rows = []
    for q in questions:
        banned = list(q.get("must_not_mention", []))
        if q.get("hide_demographics_of"):
            f = store.df.loc[q["hide_demographics_of"]]
            if 10 <= (f["age"] or 0) <= 90:
                banned.append(str(int(f["age"])))
        for _ in range(a.repeats):
            ans = planner.ask(q["question"])
            names = [c.name for c in ans.tool_calls]
            tools_ok = (not names if q.get("expect_no_tools") else
                        any(n in names for n in q["expect_any_of"]) if "expect_any_of" in q else
                        all(matched(e, ans.tool_calls) for e in q.get("expect_calls", [])))
            ok = {"tools_and_args": tools_ok, "raw_grounded": ans.grounded, "must_not_mention": not mentions_any(ans.answer, banned)}
            rows.append({"id": q["id"], "success": all(ok.values()), **ok, "steps": ans.steps, "tool_calls": names,
                         "args": [c.arguments for c in ans.tool_calls], "checks": ans.checks, "latency_ms": ans.meter.latency_ms,
                         "cost_usd": ans.meter.cost_usd, "answer": ans.answer})
            print(f"{'PASS' if rows[-1]['success'] else 'FAIL'} {q['id']:<28} {ans.meter.latency_ms:>7.0f} ms  tools={names}", flush=True)
    lat = [r["latency_ms"] for r in rows]
    per_q = {}
    for r in rows:
        per_q.setdefault(r["id"], []).append(r["success"])
    A = cfg["agent"]
    report = {"model": planner.model, "reasoning_effort": planner.reasoning_effort, "questions": len(questions), "repeats": a.repeats,
              "task_success": round(float(np.mean([r["success"] for r in rows])), 3),
              "tool_and_args_accuracy": round(float(np.mean([r["tools_and_args"] for r in rows])), 3),
              "raw_grounded": round(float(np.mean([r["raw_grounded"] for r in rows])), 3),
              "avg_steps": round(float(np.mean([r["steps"] for r in rows])), 2),
              "avg_tool_calls": round(float(np.mean([len(r["tool_calls"]) for r in rows])), 2),
              "latency_ms_p50": round(float(np.percentile(lat, 50)), 0), "latency_ms_p95": round(float(np.percentile(lat, 95)), 0),
              "cost_per_1000_usd": round(1000 * float(np.mean([r["cost_usd"] for r in rows])), 3),
              "budget_cost_per_1000_usd": A["budget_cost_per_1000"], "budget_p95_ms": A["budget_p95_ms"], "gate_task_success": A["gate_task_success"],
              "per_question": {k: f"{sum(v)}/{len(v)}" for k, v in per_q.items()},
              "failures": [{k: r[k] for k in ("id", "tools_and_args", "raw_grounded", "must_not_mention", "tool_calls", "args", "checks", "answer")}
                           for r in rows if not r["success"]]}
    report["passed"] = (report["task_success"] >= A["gate_task_success"] and report["cost_per_1000_usd"] <= A["budget_cost_per_1000"]
                        and report["latency_ms_p95"] <= A["budget_p95_ms"])
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=1))
    for f in report["failures"]:
        print("FAILED", json.dumps(f, default=str)[:700])
    Path("data/outputs").mkdir(parents=True, exist_ok=True)
    Path("data/outputs/p5_agent_eval.json").write_text(json.dumps(report, indent=1, default=str))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
