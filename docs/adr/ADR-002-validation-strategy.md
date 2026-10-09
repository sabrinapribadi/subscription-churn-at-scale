# ADR-002: Validation Strategy — Out-of-Time Cohorts, PR-AUC, and Profit@k

**Status:** Proposed
**Date:** 2026-10-09
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

Churn is a minority class (single-digit % in the official cohorts), and the model will be used on *future* expiry cohorts. The validation design must answer two questions: **"Does the model rank future churners above non-churners?"** and **"Does the ranked list capture more revenue than a simpler ordering?"**

## Decision Drivers

- Class imbalance makes accuracy and ROC-AUC optimistic; PR-AUC reflects precision where the team actually works (the top of the list)
- Random row splits leak member behaviour across train/test and overstate performance
- The business consumes a top-k list, so the metric must be evaluated at k
- Each phase gate must be falsifiable and fixed before training

## Considered Options

**Split:**
- **Random split** — Rejected: same members and same months on both sides
- **Group split by member** — Rejected as primary: still mixes time periods
- **Out-of-time by expiry cohort** — Chosen: train on cohorts ≤ t, validate on t+1, test on t+2

**Metric:**
- **Accuracy / log-loss** — Rejected as primary (imbalance); log-loss kept for calibration
- **ROC-AUC** — Secondary only
- **PR-AUC** — Chosen as primary classification metric
- **Profit@k / NDCG@k** — Chosen for ranking (Phase 4)

## Decision Outcome

- **Primary:** out-of-time PR-AUC on the test cohort
- **Ranking:** profit@top-10% where profit = Σ (save_rate × next-period revenue) − contact_cost over contacted members; `save_rate` and `contact_cost` are explicit, documented assumptions in `configs/default_config.yaml` and varied in a sensitivity table
- **Calibration:** reliability curve + Brier score on the test cohort

**Pre-registered gates:**

| Phase | Gate |
|-------|------|
| P0 | Reconstructed labels agree ≥ 99% with official labels |
| P3 | PR-AUC(GBM + embeddings) ≥ PR-AUC(GBM only) + 0.02 on the test cohort |
| P4 | profit@10%(LambdaMART) > profit@10%(sort by churn probability) across the sensitivity grid's central case |

**Falsification conditions:**

| Result | Diagnosis | Next Action |
|--------|-----------|-------------|
| Val PR-AUC ≫ test PR-AUC | Drift between cohorts | Report drift; add rolling retraining experiment |
| Embeddings gain < 0.02 | Behaviour already captured by RFM features | Report negative result; keep embeddings for personas only |
| LambdaMART ≤ probability sort | Revenue signal too flat to reorder the list | Report; fall back to expected-value sort (p × revenue) |

## Positive Consequences

- Results reflect how the model will actually be used: next month's cohort, top of the list
- Gates are set before training, so negative results remain interpretable

## Negative Consequences

- Fewer training cohorts available for the latest test month
- Profit metric depends on stated assumptions (mitigated by a sensitivity table)

## Amendment 1 (2026-10-09)

After the P0 gate failed (ADR-001 Amendment 2), the test cohort is **Mar-2017 with official labels**. Training uses cohorts up to Feb-2017; earlier cohorts carry reconstructed labels and are kept only if they raise test PR-AUC. Validation for tuning is a member-level hold-out inside the training cohorts.

## Amendment 2 (2026-10-09) — Secondary metrics and practitioner reporting

Added **after** P1, so none of these are gates. Reported in the showcase appendix:

| Metric | Why it is reported | Source |
|--------|--------------------|--------|
| Gini (2·AUC − 1) | Familiar to practitioners and credit-risk teams | Neslin et al. (2006), JMR 43(2) |
| Top-decile lift | Standard churn-tournament metric | Neslin et al. (2006) |
| H-measure | Coherent alternative to AUC | Hand (2009), Machine Learning 77 |
| Brier, ECE, calibration curve | Probabilities will drive offers | — |
| MPC / EMPC + optimal share | Profit-maximising cut-off | Verbeke et al. (2012), EJOR 218(1); Verbraken et al. (2013), IEEE TKDE 25(5) |

**Finding that motivated this:** on the realistic setup, Gini (0.600) rated the model *below* the rule (0.607) while PR-AUC (0.505 vs 0.342) and top-5% capture (45% vs 30%) favoured the model. Gini stays secondary; decisions use PR-AUC and capture at the call budget.

**Practitioner translation (rule R9):** precision@10% → "48 of 100 calls reach a leaver"; recall@10% → "2 in 3 leavers reached"; capture curve → budget dial.

## Related Decisions

- ADR-001: Task framing (defines cohorts and snapshot dates; Amendment 2 sets label sources)
