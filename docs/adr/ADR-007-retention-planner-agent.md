# ADR-007: One Tool-Using Agent (Retention Planner), Not a Multi-Agent System

**Status:** Accepted — 45/45 live test runs passed; cost and latency within budget
**Date:** 2026-10-13
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

P5 serves scores, reasons, call lists and what-if curves as typed tools (ADR-005, ADR-006). The only LLM step so far writes a note for one member. That step decides nothing, so it is not an agent. A retention manager's questions span several tools: *"Find the best share to call at a 20% save rate, then give me the first three members."*

The question: **"Should the project add LLM agents, and if so, how many?"**

## Decision Drivers

- Answers must stay faithful: every number comes from a tool, never from the model
- Cost and latency are budgeted before building and measured after (portfolio rule R13)
- Each LLM round trip costs about 1.6 s of network time from the test machine (ADR-006)
- The work is sequential (question → tools → answer); nothing runs in parallel
- Reuse the tool registry already served over MCP, so apps, MCP clients and the agent share one source of truth

## Considered Options

| Option | Evidence | Verdict |
|--------|----------|---------|
| No agent; MCP tools only for outside assistants | — | Rejected: the project would not show tool selection, grounding or evaluation of an agent |
| **One tool-using agent with a grounding guard** | Vendor engineering guidance favours the simplest design that works and adds agents only when one cannot cope | **Chosen** |
| Several agents (planner, analyst, writer, critic) | Cemri et al. (2025), *Why Do Multi-Agent LLM Systems Fail?* (arXiv 2503.13657): 14 failure modes across 7 multi-agent frameworks and 200+ tasks, in three groups: specification issues, inter-agent misalignment, and task verification | Rejected here: each agent adds round trips (about 6–10 s per answer with four) and cost; the critic role is already filled by a deterministic grader; no parallel work to split. Kept for a later project with independent sources to read in parallel |

## Decision Outcome

- **Agent** (`src/genai/agent.py`, `RetentionPlanner`): OpenAI Responses API with function calling over the four registry tools (`member_risk`, `why_at_risk`, `call_list`, `what_if`). At most 4 LLM rounds; the last round must answer in text.
- **Tool errors go back to the model as data** (unknown member, bad arguments), so it can correct itself or say what it could not find.
- **Grounding guard:** every number in the answer must match a number in the question or a tool result, within the rounding the answer shows (12.4M matches 12,431,437; 21.5% matches 0.215). No demographic words unless the question used them. At most 120 words. If any check fails, the answer is rebuilt from the last tool result by a template, and the response says so (`grounded_fallback`).
- **Served** as `POST /ask` on explain-svc (503 when no LLM key is set). Every answer returns its tool calls, LLM rounds, tokens, cost and latency.
- **Tool descriptions are part of the design:** parameter descriptions and "use this for…" hints live in the registry, so MCP clients get them too.

**Budgets (set before the first live run):** ≤ $1.00 per 1,000 questions, including nested note-writer calls; p95 ≤ 8 s; task success ≥ 80% on the live question set.

## Evaluation

`tests/llm_eval/planner_questions.json`: 15 manager questions, each run 3 times (`make agent-eval`). A run succeeds only when the agent called the expected tools with the expected arguments (±3%), its own answer passed the guard before any fallback, and it named nothing it must not. The set covers plain-words inputs ("1 in 5"), comparisons, two-step chains (what-if → call list; call list → reasons), an unknown member, a question with no numbers (defaults must be stated), an off-topic question, and a prompt-injection attempt asking for a member's gender and age.

CI tests the loop with a scripted LLM (no key): tool dispatch, error feedback, forced final answer, guard and fallback, and the endpoint contract.

## Results (2026-10-13)

Live run: `gpt-6-luna`, reasoning effort `none`, real serving artefacts (862,158 members), notes written by the live LLM inside `why_at_risk`.

| Measure | Result | Budget |
|---|---|---|
| Task success (right tools and arguments, own answer passed the guard) | **45/45 (100%)**, every question 3/3 | ≥ 80% ✅ |
| Answers that needed the fallback | 0 | reported |
| Cost per 1,000 questions (incl. nested notes) | **$0.22** | ≤ $1.00 ✅ |
| Latency p50 / p95 | 3.9 s / **6.6 s** | p95 ≤ 8 s ✅ |
| LLM rounds · tool calls per question | 2.0 · 1.1 | ≤ 4 rounds |

**How we got there:** the first run (15 questions × 1) passed 13/15, cost $1.11 per 1,000 and had a p95 of 7.5 s.

1. *Compare 5% vs 15%:* the agent asked for a 1,000,000-member list, was rejected by validation, then pulled two 500-member lists. That cost tokens, and it quoted a difference it computed itself. Fix: `limit` capped at 50 with a default of 5; parameter descriptions; the instruction "quote tool numbers, do not calculate new ones".
2. *"Profit if we call 2%":* the agent used `what_if` (best share only) instead of `call_list`. Fix: each tool's description now says when to use it ("use call_list for the profit of a specific share").

Both fixes live in the tool registry, so MCP clients get the clearer descriptions too.

**Caveat:** the same 15 questions found the fixes, so the 45/45 is not a held-out score. The next check is a fresh set of questions written without looking at the agent's answers.

## Consequences

- Positive: one agent, one guard, one evaluation; every answer is traceable to tool calls
- Negative: the strict number check rejects answers that compute new numbers (differences, totals), so the agent is told to quote tool numbers instead; a comparison is shown side by side rather than as a difference
- Negative: live answers take several seconds (2–3 round trips); fine for a planning question, too slow for a live call screen

## References

- Cemri, M. et al. (2025). Why Do Multi-Agent LLM Systems Fail? arXiv 2503.13657
- OpenAI API documentation: Responses API, function calling
- Model Context Protocol, Python SDK v2
- ADR-005 (service boundaries), ADR-006 (GenAI module and note grader)
