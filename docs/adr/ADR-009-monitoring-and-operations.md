# ADR-009: Operating the Model Monthly — Dashboard, Drift Check, Held-Out Agent Questions

**Status:** Accepted — G1–G4 passed (2026-10-13)
**Date:** 2026-10-13
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

P6 put the champion on Databricks with a registry and result tables. A retention team runs this every month: it needs to see the list, know when the data has shifted enough to distrust the scores, and trust the planning agent on questions nobody tested it on. P5's agent score (45/45) used the same questions that found its fixes, so it is not a held-out score.

The question: **"Can the team see this month's list and the model's health without an engineer, and does the agent hold up on fresh questions?"**

## Decision Drivers

- Everything runs from the same bundle and tables as P6; no hand-built dashboards
- Drift check must be cheap, explainable to practitioners, and computed for every model input
- Labels arrive late: the realised-vs-expected check is a lagged check, run once outcomes mature
- Free Edition quota: schedules exist in code but stay paused

## Considered Options

| Option | Verdict |
|---|---|
| Dashboard built by hand in the UI | Rejected: not versioned, not reproducible |
| **Dashboard as a file in the repo, deployed by the bundle** | **Chosen** |
| Drift by model performance only (needs labels) | Rejected as the only check: labels arrive 30+ days late |
| Kolmogorov–Smirnov per feature | Rejected as primary: very sensitive at 860k rows (everything is "significant") |
| **Population Stability Index (PSI) per feature and for the score**, with the usual 0.10 / 0.25 bands | **Chosen**: one number per feature, banded, familiar to risk and CRM teams |
| Re-test the agent on the P5 questions | Rejected: they found the fixes, so they cannot score them |
| **15 new questions, written and committed before any run** | **Chosen** |

## Decision Outcome

- **Drift** (`src/monitoring/drift.py`): PSI = Σ (a − e) · ln(a / e) over 10 quantile bins of the reference (training) cohort, with a small floor for empty bins; missing values get their own bin. Bands: < 0.10 stable, 0.10–0.25 watch, > 0.25 alert. Computed for every model feature and for the calibrated score, February (training) → March (scored). A lagged check compares expected churners on the list (sum of calibrated probabilities) with the churners that actually happened, once March outcomes are in.
- **Dashboard** (`dashboards/churn_monthly.lvdash.json`, bundle resource): headline counters (members, calls on the list, value at risk on the list), risk mix, top of the call list, and the drift table.
- **Job:** a `monitor_drift` task after training writes `workspace.churn.drift_psi`; a monthly schedule is defined and paused.
- **Agent:** `tests/llm_eval/planner_questions_holdout.json`, 15 questions written before any run, scored with the same rules as ADR-007.

## Gates (written before the work)

| # | Check | Pass if |
|---|---|---|
| G1 | Dashboard deployed from the bundle | Its counters equal the scores table: 862,158 members, 86,215 calls, value at risk on the list 60,918,657 |
| G2 | Drift check complete | PSI for 100% of model features and the score; every feature banded; the alert rule (PSI > 0.25) evaluated and reported, whatever it finds |
| G3 | Lagged check reported | Expected vs realised churners on the top-10% list, with the gap explained |
| G4 | Held-out agent questions | Task success ≥ 80% over 15 new questions × 3 runs; ≤ $1.00 per 1,000 questions; p95 ≤ 8 s (ADR-007 budgets) |

G2 and G3 test that monitoring works, not that there is no drift: February → March is known to have shifted (+1.7 points of churn).

## Results (2026-10-13)

| # | Check | Result | |
|---|---|---|---|
| G1 | Dashboard counters = scores table | 862,158 members · 86,215 calls · 60,918,657 value at risk · 33,808 expected and 40,300 actual churners on the list, from the dashboard's own queries | ✅ |
| G2 | PSI for every feature and the score | 30/30 features + score; 28 stable, 1 watch, 2 alert; score PSI 0.014 (stable). Databricks and local identical to 4 decimals | ✅ |
| G3 | Lagged check | List expected 33,808 churners, 40,300 happened: 16% short, because scores still run low (ADR-004) | ✅ |
| G4 | Held-out agent questions | 42/45 (93%) · $0.21 per 1,000 · p95 6.3 s | ✅ |

**What the alerts mean.** `days_since_last_tx` (PSI 1.81) and `tenure_days` (0.43) crossed 0.25, yet the score barely moved. Most members are on 30-day auto-renew plans. February expiries were last charged in January (31 days), March expiries in February (28 days), so on scoring day (expiry − 14) the typical value moved from 17 to 14 days. That is a calendar effect, not a change in behaviour; tenure grows by a month for the same members. Recommendation for the next model: express recency relative to the billing cycle (e.g. days since the last charge minus the plan length), so short months stop looking like drift.

**The three held-out failures** are one question ("Is it worth calling 30%… at 60 per call?"). The agent used the right tool and arguments and answered "expected profit is -7,245,823", which is correct. The number check dropped the minus sign and rejected it, so the guard showed the tool-built answer instead. The check now keeps signs (with a test). The score is reported as measured, 42/45; re-scoring the same questions after the fix would no longer be a held-out score.

**Platform notes.** LightGBM saves models by appending to the file, which Unity Catalog volumes do not support; the job now saves to local disk and copies. That failure happened after registration, so model versions 4 and 5 exist from those attempts (same model); version 6 holds `champion`.

**Operations.** The job (`databricks.yml`) has a monthly schedule (5th of the month, 06:00 UTC), paused on Free Edition. The dashboard is deployed by the same bundle.

## References

- Siddiqi, N. (2006). *Credit Risk Scorecards: Developing and Implementing Intelligent Credit Scoring.* Wiley (population stability index and its 0.10 / 0.25 bands)
- Databricks AI/BI dashboards and Asset Bundles: https://docs.databricks.com/aws/en/dev-tools/bundles/
- ADR-007 (agent budgets and scoring rules), ADR-008 (job, tables, registry)
