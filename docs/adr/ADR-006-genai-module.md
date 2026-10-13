# ADR-006: GenAI Module — Provider Interface, Versioned Prompts, Shared Tools, Grounding Grader

**Status:** Accepted — evaluation set 100% grounded (12/12 live on OpenAI); cost within budget; live latency p95 2.26 s misses the 2 s budget (see Results)
**Date:** 2026-10-12
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

A CRM agent asks "why is this member at risk?" The model can answer with feature contributions, which agents cannot read. A language model can turn them into a sentence — but it can also invent reasons or numbers, and recent work warns that fluent explanations raise trust without improving decisions.

The question: **"How do we write plain-language reasons that are provably faithful to the model, testable without a paid API, and swappable between providers?"**

## Decision Drivers

- Faithfulness: every reason and number in the text must come from the model output
- Testable in CI without an API key or network
- Provider-agnostic (OpenAI chosen for now — portfolio decision D4)
- One tool definition used by both the MCP gateway and LLM function calling
- Structured reasons stay visible next to the text, never replaced by it

## Considered Options

| Option | Evidence | Verdict |
|--------|----------|---------|
| Show raw SHAP values only | — | Rejected: unreadable for agents |
| Free-form LLM narration | Explingo narrator (Zytek et al., 2024, arXiv 2412.05145) | Rejected alone: no guarantee of faithfulness |
| **Narrator + grader**, with deterministic fallback | Explingo pairs a narrator with a grader; "Quality Without Usefulness" (arXiv 2605.26770, 2026) warns narratives act as trust heuristics | **Chosen**, with a *rule-based* grader so CI is deterministic |

## Decision Outcome

- **Providers** (`src/genai/providers.py`): `TemplateProvider` (deterministic text from reasons; no key) and `OpenAIProvider` (model from config). `get_provider()` uses OpenAI only when `OPENAI_API_KEY` is set.
- **Prompts** (`src/genai/prompts/*.yaml`): versioned (`name`, `version`, `system`, `user`); the version is returned with every explanation and is part of the cache key. One file per prompt, renamed in place when the version changes (git keeps earlier versions).
- **Grader** (`src/genai/grader.py`), all must pass:
  1. *Numbers grounded* — every number in the text appears in the supplied facts
  2. *Reasons grounded* — the top reason is mentioned; no feature outside the supplied reasons is named
  3. *Length* — ≤ 90 words
  4. *Action* — ends with exactly one action from an allowed list
- **Guard:** if the provider's text fails the grader, explain-svc returns the template text and `grounded_fallback=true`.
- **Tool registry** (`src/genai/tools.py`): typed functions registered once; exported to MCP (`MCPServer.tool`) and as OpenAI function schemas.
- **LLM evaluation set** (`tests/llm_eval/cases.json`): member cases with expected properties; CI runs it with `TemplateProvider`; `make llm-eval` runs it against OpenAI when a key is present and reports the raw pass rate before the guard.

**Gate:** 100% of evaluation cases grounded after the guard in CI; OpenAI raw pass rate reported, not gated.

## Cost and latency budgets (portfolio rule R13)

Prices from OpenAI's official pricing page (developers.openai.com/api/docs/pricing, read 2026-10-12), kept in `configs/default_config.yaml`:

| Model (default) | Input / 1M tokens | Cached input | Output | Batch API |
|---|---|---|---|---|
| `gpt-6-luna` | $0.10 | $0.01 | $0.50 | −50% |

Measured per explanation ≈ 200 input + 56 output tokens → **≈ $0.00005 each, $0.048 per 1,000**; the full monthly call list (86,215 members) ≈ $4, or ≈ $2 as a nightly batch. (Planning estimate before the live run: $0.10 per 1,000.)

| Budget | Target | How it is enforced |
|---|---|---|
| Cost | ≤ $0.20 per 1,000 explanations | Every call records tokens and estimated cost; `make llm-eval` reports cost per 1,000 |
| Latency, cached or template path | p95 ≤ 50 ms | Tested in CI |
| Latency, live LLM call | p95 ≤ 2.0 s | Reported by `make llm-eval` when a key is present |

**Cost levers designed in:** (1) cache keyed by member + model version + prompt version — a repeat question costs nothing; (2) nightly batch precomputation for the call list, so agents never wait on the LLM; (3) the smallest model that passes the evaluation set; (4) the template provider as a free, instant fallback.

## Results (2026-10-12)

- Evaluation set (12 cases, template provider): raw pass 100%, grounded after guard 100%, action accuracy 100%.
- Guard verified with a scripted OpenAI client: invented facts → fallback to the template; grounded text → used and metered.
- Latency (real artefacts): first note p95 49 ms in-process, 80 ms over HTTP; cached p95 0.13 ms in-process, 7 ms over HTTP.
- Cost: template $0.

### Live OpenAI run (2026-10-13, `gpt-6-luna`, prompt `explain_member.v2`)

| Metric | Result | Budget |
|---|---|---|
| Raw pass rate (before the guard) | **12/12 (100%)** | reported |
| Grounded after guard · action accuracy | 100% · 100% | 100% |
| Cost per 1,000 notes | **$0.048** (≈ 198 input + 56 output tokens) | ≤ $0.20 ✅ |
| Live latency p50 / p95 | 1.69 s / **2.26 s** | p95 ≤ 2.0 s ❌ |
| Network floor ("Say OK", 10 calls) | 1.40 s / 1.60 s | — |

How we got there, in three runs:

1. **First run failed:** the API rejected `temperature` for this model. It is now optional in config (`null`) and sent only when set.
2. **Raw pass 25%, p95 3.6 s:** `gpt-6-luna` is a reasoning model, and reasoning tokens (80–140) used up the 160-token output limit, cutting notes off mid-sentence. Fixed with `reasoning_effort: none` (config).
3. **Raw pass 5/12:** the model paraphrased reasons ("a 410-day plan" for "plan length in days"), which the exact-match grader rejects. Prompt v2 asks for each reason's exact wording, first reason first, risk level and percentage up front, so the grader stays strict and the prompt adapts to it. The eval's banned-word check now matches whole words (a banned "19" had fired inside "2190").

**Latency decision:** the 2 s budget is kept, and the miss is recorded. About 1.6 s of the p95 is the network round trip, so a faster model would not fix it. Agents do not wait on this path: call-list notes are written in the nightly batch, and repeat questions are cached (7 ms over HTTP). The live path serves only first-time, on-demand questions. The next lever, if needed, is streaming, so the first words appear before the full note.

## Consequences

- Positive: no explanation can reach an agent with an invented reason or number; CI never depends on a paid API
- Negative: rule-based grading is stricter than an LLM grader and may reject acceptable paraphrases (falls back to the template, which is always faithful)

## References

- Zytek et al. (2024). Explingo: Explaining AI Predictions using Large Language Models. arXiv 2412.05145
- Quality Without Usefulness: LLM-Generated XAI Narratives as Trust Heuristics Rather Than Decision Aids (2026). arXiv 2605.26770
- Model Context Protocol, Python SDK v2 (`mcp.server.mcpserver.MCPServer`)
