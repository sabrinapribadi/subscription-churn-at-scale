# Architecture Decision Records

This directory documents the key design decisions for the subscription churn project. Each ADR captures the context, options considered, decision, and consequences — written before implementation, not after.

## Index

| # | Title | Status | Summary |
|---|-------|--------|---------|
| [ADR-001](ADR-001-task-framing.md) | Point-in-time snapshots k days before expiry | Proposed | Predict at expiry − k days (k ∈ {7, 14, 30}) with observation window W tested over {30…180}; labels reconstructed from transactions and validated against official labels (≥ 99% gate). |
| [ADR-002](ADR-002-validation-strategy.md) | Out-of-time cohorts, PR-AUC, profit@k | Proposed | Train on earlier expiry cohorts, test on later ones; PR-AUC primary; profit@top-10% for ranking with explicit save-rate and contact-cost assumptions; gates pre-registered per phase. |
| ADR-003 | Behavioural encoder design | Planned (P3) | — |
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
