# ADR-012: Agent Skill for the Call Planner (R24)

**Status:** Accepted
**Date:** 2026-11-17
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

- The public demo serves four tools over REST and MCP (ADR-010), but an AI agent does not know when to use them or how to read their numbers.
- Several numbers are easy to misread:
  1. `call-list` is a forecast from calibrated churn chances; `what-if` is a backtest on March 2017 members who actually churned. They give different best shares (26% vs 34% at a 25% save rate and NT$15 per call).
  2. Save rate and cost per call are assumptions, not data, and drive every profit figure.
  3. Member value is 12 months of revenue in New Taiwan dollars (NT$), not a lifetime value.
  4. Reasons are TreeSHAP log-odds contributions, not percentages.
- **Question:** how can any coding or chat agent use the planner correctly, with proof that it does?

## Decision Drivers

- Agents answer from the API's numbers only and decline to score real members (competition data terms, ADR-010).
- Works without installing packages or holding keys; free to run (R20).
- Tested like the rest of the project (R19, R24), with the same answer structure as the other portfolio skills.

## Considered Options

| Option | Chosen | Why |
|---|---|---|
| **Agent Skill (`SKILL.md`) + dependency-free client + evals** | **Yes** | Portable across agents that read skills; carries the reading rules; testable |
| MCP server only (already live) | No | Gives the tools but not when to use them or how to read the numbers |
| Paid skill marketplace listing | No | Competition data terms are non-commercial; employment terms |

## Decision

- `skills/churn-call-planner/`:
  - `SKILL.md`: trigger description, workflow (`about` first), reading rules, answer structure, limits.
  - `scripts/churn.py`: standard library only; one retry for cold starts; member ids fully URL-quoted; a 404 comes back as data (`not_found`).
  - `scripts/charts.py`: three self-contained chart forms chosen by the reader's job: a line of expected profit by share called (best share marked), diverging bars for what raises and lowers a member's risk, ranked bars for backtest profit by ranking method. Colour-vision-checked palette, hover values and a table view.
  - `references/data-sources.md` (cohort, period, definitions, the baseline table, assumptions, privacy) and `references/charts.md`.
- `evals/`: four task cases in the `claude plugin eval` layout (budget of 50,000 calls, explain a demo member, ranking vs today's rule, out-of-scope real member) with 20 graders; `trigger-evals.json` with 10 should-trigger and 10 near-miss prompts.
- **Baseline stated in every ranking answer:** today's rule (manual renewers first, then the longest idle) reaches 54.1% of churners at 10% calls; the model reaches 65.2–65.5%.
- CI: `tests/test_skill_client.py` (routes, id quoting, charts, skill files; offline); `tests/test_no_member_ids.py` now also scans `skills/`; `scripts/skill_live_check.py` after every deploy.

## Empirical Results (2026-11-17, iteration 1)

- Task cases: **23 of 23** checks pass, verified by script against the live API (`grade.py` reads each figure from the API, not from the answer).
- Runs were done by the session that wrote the skill, so there is no independent no-skill baseline yet; `claude plugin eval` gives one.
- Corrections found while writing it (R23):
  1. Amounts are NT$ (the dataset's documented currency), not an unnamed unit.
  2. The value-vs-chance margin is NT$23,000 a month (65.6% vs 65.5% of value at risk), so it is called small, not a win.
  3. The profit sweep was widened from 1–30% to 2–60% because the best share sat at the edge.
  4. An invented reason ("genres you like") was removed from the call-script idea; scripts use only the API's reasons.
- A bug found by the new offline test: `urllib.parse.quote` keeps `/` by default, so an id like `a/b` changed the path; now quoted with `safe=""`.

## Consequences

- **Positive:** any agent that reads skills can plan a call list with the right caveats; the evals and live check fail when the snapshot changes, so the graders are not left stale.
- **Negative:** the skill only serves the 2017 cohort and synthetic members; a live call test is still the missing evidence (ADR-011, open item).
- **Revisit when:** the snapshot is rebuilt, a reviewer's feedback round lands, or an independent `claude plugin eval` run disagrees with the scripted grading.
