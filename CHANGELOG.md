# Changelog

Newest first. Each entry uses STAR (Situation, Task, Action, Result) so it can be told as a story.

## [0.1.0] — 2026-10-09 — Project design: framing, validation, phases
**Files:** README.md, docs/PRD.md, docs/adr/README.md, docs/adr/ADR-001-task-framing.md, docs/adr/ADR-002-validation-strategy.md, configs/default_config.yaml, Makefile, .gitignore, .env.example
- **Situation:** The best-known public churn benchmark (WSDM Cup 2018) predicts churn at the expiry date, ranks by probability, and is usually evaluated on random splits — none of which match how a retention team works.
- **Task:** Design a churn system that predicts early enough to act, is evaluated on future cohorts, and ranks by money at stake — with every success criterion fixed before training.
- **Action:** Reframed the task as point-in-time snapshots k days before expiry (ADR-001), grounded in two 2026 papers showing temporal framing and window length matter more than model choice. Chose out-of-time cohort validation with PR-AUC and profit@top-10% (ADR-002). Defined 8 phases, each with a falsifiable gate. Rejected: competition framing (zero lead time), random splits (leakage), accuracy/ROC-AUC as primary (imbalance).
- **Result:** Design complete; 2 ADRs, PRD v0.1, 4 pre-registered gates. No data processed yet.
- **Talking point:** "Before modelling, I changed the question: not 'will they churn?' but 'who should we call two weeks before renewal, and in what order?'"
