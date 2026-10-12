# Architecture Decision Records

This directory documents the key design decisions for the subscription churn project. Each ADR captures the context, options considered, decision, and consequences — written before implementation, not after.

## Index

| # | Title | Status | Summary |
|---|-------|--------|---------|
| [ADR-001](ADR-001-task-framing.md) | Point-in-time snapshots k days before expiry | Amended | Predict at expiry − k days (k ∈ {7, 14, 30}) with observation window W tested over {30…180}; labels reconstructed from transactions. **Amended:** P0 gate failed (98.8% / 97.0%); official labels are test truth, rebuilt labels are training augmentation only. |
| [ADR-002](ADR-002-validation-strategy.md) | Out-of-time cohorts, PR-AUC, profit@k | Proposed | Train on earlier expiry cohorts, test on later ones; PR-AUC primary; profit@top-10% for ranking with explicit save-rate and contact-cost assumptions; gates pre-registered per phase. |
| [ADR-003](ADR-003-behaviour-encoder.md) | Behaviour signal: shape statistics vs masked autoencoder vs Mantis | Accepted (gate failed) | Three arms added to the P2 model (k = 14, W = 30); gate +0.02 PR-AUC on Mar-2017; arm C on a 100k sample (Amendment 1); personas as practitioner output. |
| ADR-004 | Ranking objective and relevance labels | Planned (P4) | — |
| ADR-005 | Service boundaries and contracts | Planned (P5) | — |
| ADR-006 | GenAI module: provider, prompts, tool registry | Planned (P5) | — |

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
