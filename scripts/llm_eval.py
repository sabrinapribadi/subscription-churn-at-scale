"""LLM evaluation set with cost and latency report (ADR-006, rule R13).

    python scripts/llm_eval.py                     # free template provider (what CI runs)
    OPENAI_API_KEY=... python scripts/llm_eval.py --provider openai

Reports: raw pass rate (before the guard), grounded rate after the guard (gated at 100%),
action accuracy, latency p50/p95, tokens, and cost per 1,000 explanations vs the budget.
Exit code 1 if a gate or budget fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.genai.explain import Explainer, build_facts  # noqa: E402
from src.genai.grader import grade, mentions_any  # noqa: E402
from src.genai.providers import get_provider  # noqa: E402
from src.services.contracts import Reason, Reasons, Score  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--provider", choices=["template", "openai"], default="template"); a = ap.parse_args()
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())["llm"]
    prov = get_provider(cfg, prefer=a.provider)
    if a.provider == "openai" and prov.name != "openai":
        sys.exit("OPENAI_API_KEY is not set; refusing to report template results as OpenAI results.")
    cases = json.loads(Path("tests/llm_eval/cases.json").read_text())
    raw_ok, grounded, action_ok, lat, cost, tin, tout, failed = [], [], [], [], [], [], [], []
    for c in cases:
        s = Score(member_id=c["id"], churn_probability=c["p"], risk_level=c["risk"], member_value=c["value"],
                  expected_value_at_risk=c["p"] * c["value"], priority_rank=1, priority_percentile=100, expiry_date=c["expiry"], model_version="eval")
        rs = Reasons(member_id=c["id"], model_version="eval", reasons=[Reason(**r) for r in c["reasons"]])
        facts = build_facts(s, rs)
        ex = Explainer(prov)
        system, user = ex.prompt.render(facts)
        out = prov.complete(system, user, facts)
        checks = {k: v for k, v in grade(out.text, facts).items() if not v}
        if mentions_any(out.text, c["must_not_mention"]):
            checks["must_not_mention"] = False
        raw_ok.append(not checks)
        if checks:
            failed.append({"id": c["id"], "failed": sorted(checks), "text": out.text})
        e = ex.explain(s, rs)
        grounded.append(e.grounded and not mentions_any(e.narrative, c["must_not_mention"]))
        action_ok.append(e.suggested_action == c["expected_action"])
        lat.append(out.meter.latency_ms); cost.append(out.meter.cost_usd); tin.append(out.meter.input_tokens); tout.append(out.meter.output_tokens)
    per_1000 = 1000 * float(np.mean(cost))
    budget_ms = cfg["budget_p95_ms_live"] if prov.name == "openai" else cfg["budget_p95_ms_cached"]
    report = {"provider": prov.name, "model": prov.model, "cases": len(cases),
              "raw_pass_rate": round(float(np.mean(raw_ok)), 3), "grounded_after_guard": round(float(np.mean(grounded)), 3),
              "action_accuracy": round(float(np.mean(action_ok)), 3),
              "latency_ms_p50": round(float(np.percentile(lat, 50)), 1), "latency_ms_p95": round(float(np.percentile(lat, 95)), 1),
              "avg_input_tokens": round(float(np.mean(tin)), 1), "avg_output_tokens": round(float(np.mean(tout)), 1),
              "raw_pass_by_source": {src: f"{sum(r for r, x in zip(raw_ok, cases) if x.get('source', 'edge') == src)}/{sum(x.get('source', 'edge') == src for x in cases)}"
                                     for src in sorted({x.get("source", "edge") for x in cases})},
              "cost_per_1000_usd": round(per_1000, 4), "budget_cost_per_1000_usd": cfg["budget_cost_per_1000"], "budget_p95_ms": budget_ms}
    report["passed"] = report["grounded_after_guard"] == 1.0 and report["action_accuracy"] == 1.0 and per_1000 <= cfg["budget_cost_per_1000"] and report["latency_ms_p95"] <= budget_ms
    report["raw_failures"] = failed
    print(json.dumps(report, indent=1))
    Path("data/outputs").mkdir(parents=True, exist_ok=True)
    Path(f"data/outputs/p5_llm_eval_{prov.name}.json").write_text(json.dumps(report, indent=1))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
