# ADR-005: Service Boundaries and Contracts

**Status:** Accepted — gate passed
**Date:** 2026-10-12
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

P1–P4 produced a model, calibrated scores and a value-ordered call list, but only as notebooks and batch scripts. A CRM screen, a campaign tool and an AI assistant all need the same answers on demand: *how risky is this member, why, and who should we call first?*

The question: **"How do we serve scores, reasons and call lists so apps and AI agents get identical, typed answers?"**

## Decision Drivers

- One owner per concern: features, model, language, agent access
- Typed request/response contracts that tests can pin
- Runs on a laptop without Docker (local mode) and as containers in CI/production (HTTP mode)
- The model and its calibration are versioned artefacts, not code

## Considered Options

| Option | Verdict |
|--------|---------|
| One monolithic API | Rejected: language (LLM) and model would share failure modes and scaling |
| **Four services: features · scoring · explanation · MCP gateway** | **Chosen** |
| Serverless functions per endpoint | Deferred: P6 (Databricks) decides the hosting target |

## Decision Outcome

| Service | Owns | Endpoints |
|---------|------|-----------|
| **feature-svc** | Point-in-time feature rows per member and cohort | `GET /members/{id}/features` |
| **scoring-svc** | LightGBM model, calibration (isotonic + prior-shift), member value, priority order, per-member contributions (TreeSHAP via LightGBM `pred_contrib`) | `GET /members/{id}/score`, `GET /members/{id}/reasons`, `POST /call-list` |
| **explain-svc** | Plain-language explanation from score + reasons, through the GenAI module (ADR-006), with a grounding grader; hosts the planner agent (ADR-007) | `GET /members/{id}/explanation`, `POST /ask` |
| **mcp-gateway** | MCP tools for AI agents, from the shared tool registry | tools: `member_risk`, `why_at_risk`, `call_list`, `what_if` |

- **Contracts:** pydantic models in `src/services/contracts.py` are the single source of truth; every endpoint declares its response model; contract tests pin field names and types.
- **Clients:** `LocalClient` (in-process) and `HttpClient` (service URLs from env) implement the same interface, so the gateway and explain-svc run identically in tests and in containers.
- **Artefacts:** `scripts/export_serving_artifacts.py` writes model, calibration and the scored cohort to `SERVING_DIR` (outside the repo); tests build tiny synthetic artefacts.
- **Health:** every service exposes `GET /health` with model version and row count.

**Gate (P5, from the PRD):** contract tests and the LLM evaluation set pass in CI.

## Results (2026-10-12)

| Check | Result |
|---|---|
| Serving store reproduces P4 | Top-10% realised profit 12,431,437, identical to P4 (re-exported 2026-10-13 after the ADR-008 determinism fixes; first export 12,458,816) |
| End to end over HTTP (real artefacts, 862,158 members) | MCP client → gateway → explain-svc → scoring-svc: 80 ms first answer, 7 ms repeat |
| Contract tests (all endpoints, 404s, input validation, ordering) | Pass |
| MCP tools over the real protocol (in-memory and HTTP) | Pass, including clean errors for unknown members |
| Serving image has no Spark or PyTorch | Verified in a clean environment; built in CI |

**Gate:** contract tests and the LLM evaluation set pass in CI → **passed** in [GitHub Actions run 38279575714](https://github.com/sabrinapribadi/subscription-churn-at-scale/actions/runs/38279575714): 55 tests passed, 1 skipped (the PyTorch test, run locally), evaluation set 100% grounded, Docker image built. The first CI run failed at setup (pip cache had no requirements file to key on) and was fixed before the gate was claimed.

## Consequences

- Positive: each concern can be replaced alone (e.g. a new model only changes scoring-svc); agents and apps share one source of truth
- Negative: four deployables instead of one; mitigated by one image with a `SERVICE` switch and a single compose file

## Related Decisions

- ADR-004 (calibration and value ordering served by scoring-svc)
- ADR-006 (GenAI module used by explain-svc and the MCP gateway)

## References

- FastAPI documentation: https://fastapi.tiangolo.com/
- Pydantic documentation (models as contracts): https://docs.pydantic.dev/
- Model Context Protocol specification: https://modelcontextprotocol.io/
