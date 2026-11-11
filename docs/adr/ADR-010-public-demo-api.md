# ADR-010: Public Demo API, Remote MCP and Technology Assessment (R19–R21)

**Status:** Accepted — checks passed (2026-11-11)
**Date:** 2026-11-11
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

- P5 built four services and an MCP gateway; they run only in containers on a laptop.
- Portfolio rules now require CI/CD (R19), zero hosting cost (R20) and a technology assessment (R21).
- The competition's data terms forbid redistribution: no real member row may be served.
- **Question:** how can hiring teams and AI assistants try the tools publicly, for $0, without publishing member data?

## Decision Drivers

- No real member row leaves the laptop; only aggregates and synthetic members.
- No API key and no model library on the public host; public traffic never spends tokens.
- Same tool registry as P5 (`src/genai/tools.py`), so agents see the same four tools.

## Decision

### 1. What the public app serves

| Tool | Public answer |
|---|---|
| `call_list` | Real cohort totals at every 0.1% of members: members called, expected churners, value at risk, profit. No member rows. |
| `what_if` | Real P4 value-by-budget curves (already aggregate). |
| `member_risk`, `why_at_risk` | 100 synthetic members (`demo-001` … `demo-100`) with the real feature schema, scored, ranked against the real cohort and explained by the real model. |

- **Notes:** written once offline by the configured model and graded; the host serves them precomputed.
- **Not public:** feature lookups, the planning agent (`/ask`, needs a key) and real member scores.

### 2. Build and host

- `scripts/build_public_snapshot.py` builds a 0.23 MB snapshot from the real artefacts, refuses to write if any real member id is in it, and records its SHA-256.
- `scripts/build_deploy.py` bundles the light code (no LightGBM, pandas or NumPy), the snapshot and four dependencies (FastAPI, MCP, pydantic, PyYAML).
- **Host:** Vercel Hobby (free, non-commercial). The results page stays the static fallback (R20).
- **MCP:** stateless Streamable HTTP with JSON responses (spec 2026-07-28; Python SDK 2.3.0); DNS-rebinding protection on, allowing only localhost and the deployment's own hostnames.

### 3. CD (R19)

- On push to `main` after the tests and image build: build the bundle, sign its build provenance (GitHub artifact attestations), deploy, smoke-test `/health`, a demo note, a call-list total, MCP `tools/list` and an injection probe.

### 4. Technology assessment (portfolio plan §10)

| Technology | Rating | Where in CHN-1 |
|---|---|---|
| CI/CD + build provenance | Adopt | §3; error-level lint added to CI |
| Remote MCP, 2026-07-28 spec | Adopt | `/mcp` on the public app |
| Prompt-injection tests on tools | Adopt | Non-identifier inputs refused and never echoed (REST and MCP) |
| MLflow GenAI evaluation | Adopt (exists) | P5 LLM evaluation set in CI |
| OpenTelemetry GenAI traces | Trial | Pattern proven in the lithology project; add when notes are regenerated |
| Multi-agent over A2A | Hold | One planning agent answers every tested question |
| Databricks Apps | Trial | Bundle already deploys the dashboard; an app would need a workspace login |

## Empirical results (2026-11-11)

| Check | Target | Result |
|---|---|---|
| Real member ids in the snapshot | 0 | 0 (checked by the build script and a test) |
| Call-list totals vs the real service (4 shares) | Equal | Equal; at 10%: 86,215 members, 60,918,657 value at risk, same as the P7 dashboard |
| What-if vs the real service | Equal | Equal (shared function) |
| Demo notes (100, live) | All grounded | 100 of 100 grounded, 0 template fallbacks; $0.047 per 1,000 notes |
| Demo note latency (offline build) | Reported against the 2 s live budget | p95 3.2 s: **over budget**; does not affect the host, which serves them precomputed |
| Injected text (REST and MCP) | Refused, not echoed | Passed |
| MCP from an unknown host | Rejected | 421 |
| Bundle without model libraries | Starts and passes the smoke test | Passed (0.25 MB) |

- **Demo mix:** 34 high, 27 medium and 39 low risk; the riskiest demo member (78%) would rank 6,236th of 862,158 real members.

## Considered Options

| Option | Status | Why |
|---|---|---|
| **Aggregates + synthetic members on Vercel Hobby** | **Chosen** | Free; keeps the data terms; real model behaviour |
| Serve real member scores | Rejected | Redistributes competition data |
| Run LightGBM on the host | Rejected | Larger bundle, slower cold starts, and it would need member rows |
| Render | Rejected | Paid instances bill while idle (R20) |

## Consequences

- **Positive:** anyone can call the four tools from a browser or an AI assistant at $0, with no member data exposed.
- **Negative:** member lookups are synthetic; call-list shares are rounded to 0.1%; cold starts on a free host.

## Related Decisions

- ADR-005 (service boundaries), ADR-006 (GenAI module), ADR-007 (planning agent), ADR-009 (operations)

## Evidence

| Source | Issuer | Used for |
|---|---|---|
| The 2026-07-28 Specification (MCP blog) | Model Context Protocol | Stateless core, Streamable HTTP |
| Deploy a FastAPI app on Vercel (docs, updated 2026-08-27) | Vercel | Hosting |
| Artifact attestations (docs) | GitHub | Build provenance, free for public repositories |
| Top Strategic Technology Trends for 2026 (press release, 20 Oct 2025) | Gartner | AI security platforms, digital provenance |
| WSDM Cup 2018 — KKBox's Churn Prediction Challenge (competition rules) | Kaggle | Data terms: no redistribution |
