# Architecture Decision Records

This directory documents the key design decisions for the subscription churn project. Each ADR captures the context, options considered, decision, and consequences — written before implementation, not after.

## Index

| # | Title | Status | Summary |
|---|-------|--------|---------|
| [ADR-001](ADR-001-task-framing.md) | Point-in-time snapshots k days before expiry | Amended | Predict at expiry − k days (k ∈ {7, 14, 30}) with observation window W tested over {30…180}; labels reconstructed from transactions. **Amended:** P0 gate failed (98.8% / 97.0%); official labels are test truth, rebuilt labels are training augmentation only. |
| [ADR-002](ADR-002-validation-strategy.md) | Out-of-time cohorts, PR-AUC, profit@k | Proposed | Train on earlier expiry cohorts, test on later ones; PR-AUC primary; profit@top-10% for ranking with explicit save-rate and contact-cost assumptions; gates pre-registered per phase. |
| [ADR-003](ADR-003-behaviour-encoder.md) | Behaviour signal: shape statistics vs masked autoencoder vs Mantis | Accepted (gate failed) | Three arms added to the P2 model (k = 14, W = 30); gate +0.02 PR-AUC on Mar-2017; arm C on a 100k sample (Amendment 1); personas as practitioner output. |
| [ADR-004](ADR-004-ranking-and-calibration.md) | Call-list ranking and calibration | Accepted (gates failed; EV sort adopted) | Isotonic + prior-shift EM (no March labels needed); probability vs expected-value sort vs LambdaMART; gates: LambdaMART profit@10% > probability sort; ECE ≤ 0.010. EV sort wins ties. |
| [ADR-005](ADR-005-service-boundaries.md) | Service boundaries and contracts | Accepted | feature-, scoring-, explain-svc and an MCP gateway; pydantic contracts; Local and HTTP clients; one image with a SERVICE switch; gate passed. |
| [ADR-006](ADR-006-genai-module.md) | GenAI module: provider, prompts, tool registry | Accepted | Template and OpenAI providers, versioned prompts, rule-based grounding grader with template fallback, cache, shared MCP/OpenAI tool registry; cost and latency budgets (rule R13). |

## How to Read an ADR

- **Status** — Proposed / Accepted / Amended / Superseded
- **Context** — Why this decision was needed
- **Considered Options** — The realistic alternatives with pros/cons
- **Decision Outcome** — What was chosen and why, plus falsification conditions
- **Consequences** — Positive and negative downstream effects
- **Implementation Notes** — Specific code constraints that enforce the decision

## Decision Dependencies

```
ADR-001 (task framing)
  └── ADR-002 (validation — depends on cohort definition)
        └── ADR-003 (encoder — judged by the P3 gate)
        └── ADR-004 (ranking — judged by the P4 gate)
ADR-005 (services)
  └── ADR-006 (GenAI module — explain-svc and mcp-gateway consume it)
```
