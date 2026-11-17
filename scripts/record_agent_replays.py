"""Record the agent's answers for the app's replay chat (R26): real runs on the public API, saved with tools, cost and latency.

    set -a; . ./.env; set +a; python scripts/record_agent_replays.py      # needs OPENAI_API_KEY; prints cost, never the key
Writes app/replays.json. Questions come from app/agent_tools.py QUESTIONS; only public data (aggregates, demo members) is used.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import agent as A
import agent_tools as T

MAX_RESULT_CHARS = 4000          # keep each stored tool result small; the answer was made from the full one


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    from openai import OpenAI
    client = OpenAI(timeout=30)
    runs = []
    for q in T.QUESTIONS:
        r = A.run(q, client, T.TOOLS, T.SYSTEM, T.MODEL, T.PRICES)
        r["tool_results"] = [json.loads(json.dumps(x, default=str)[:MAX_RESULT_CHARS]) if len(json.dumps(x, default=str)) <= MAX_RESULT_CHARS
                             else {"truncated": json.dumps(x, default=str)[:MAX_RESULT_CHARS]} for x in r["tool_results"]]
        runs.append(r)
        print(f"{r['latency_ms']:>7.0f} ms  ${r['cost_usd']:.6f}  grounded={r['grounded']}  {q[:70]}")
    lat = sorted(r["latency_ms"] for r in runs)
    out = {"recorded_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"), "model": T.MODEL, "api": T.API,  # noqa: UP017 (3.8+)
           "runs": runs, "summary": {"questions": len(runs), "grounded": sum(r["grounded"] for r in runs),
                                     "cost_usd_total": round(sum(r["cost_usd"] for r in runs), 6),
                                     "cost_per_1000_usd": round(1000 * sum(r["cost_usd"] for r in runs) / len(runs), 4),
                                     "latency_ms_p50": lat[len(lat) // 2], "latency_ms_p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))]}}
    (ROOT / "app" / "replays.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
