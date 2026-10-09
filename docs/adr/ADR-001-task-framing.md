# ADR-001: Task Framing — Point-in-Time Snapshots k Days Before Expiry

**Status:** Proposed
**Date:** 2026-10-09
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

The WSDM Cup 2018 task asks: *for members whose subscription expires in a given month, will they fail to renew within 30 days?* Features in that framing may use everything up to the expiry date. That is fine for a leaderboard, but useless operationally — on the expiry date there is no time left to act.

The question this project must answer is: **"Which members expiring soon are at risk, early enough for a retention team to act?"**

## Decision Drivers

- A prediction is only useful if it arrives before the decision point (lead time)
- Features must be point-in-time correct: nothing after the snapshot date may leak in
- Observation-window length is design-dependent and must be measured, not assumed (arXiv 2607.00473 shows the sufficiency knee moves between 30–120 days depending on cohort, target and features)
- Temporal framing matters more than model complexity for deployability (arXiv 2606.06776)
- Multiple monthly cohorts are needed for honest out-of-time testing

## Considered Options

- **A. Replicate the competition framing (snapshot at expiry)** — Rejected as primary: zero lead time. Kept as a reference point to show the cost of lead time.
- **B. Fixed calendar snapshot (e.g. 1st of month for everyone)** — Rejected: lead time varies per member from 0 to 30 days, mixing easy and hard cases.
- **C. Member-relative snapshot at expiry − k days, multiple monthly cohorts** — Chosen.
- **D. Continuous-time survival model over full tenure** — Deferred: richer, but harder to evaluate against the official labels. Revisit as a discrete-time hazard extension once C is validated.

## Decision Outcome

For each member *m* with a membership expiring on date *E* in cohort month *c*:

- **Snapshot date** `S = E − k`, with k ∈ {7, 14, 30}; default k = 14
- **Observation window** `[S − W, S)`, with W ∈ {30, 60, 90, 120, 180}; default W = 120
- **Label** = 1 if no new valid subscription transaction within 30 days after *E* (official definition), reconstructed from transactions so that cohorts beyond the two official months can be built
- **Cohorts** = consecutive monthly expiry cohorts; the official Feb-2017 and Mar-2017 labels are used to validate reconstruction

**Falsification conditions:**

| Result | Diagnosis | Next Action |
|--------|-----------|-------------|
| Reconstructed labels agree < 99% with official labels | Label logic misses an edge case (cancel/auto-renew/overlapping plans) | Inspect disagreements by transaction pattern; amend this ADR |
| PR-AUC at k = 14 ≈ PR-AUC at k = 0 | Lead time is free — the early signal is already present | Report it; default to k = 30 for more action time |
| PR-AUC at k = 14 ≪ k = 0 (drop > 0.10) | Most signal arrives in the final two weeks | Report the trade-off curve; let the business pick k |
| Window curve flat beyond W = 30 | Long history adds nothing for this design | Use W = 30; cheaper features and serving |

## Amendment 1 (2026-10-09) — What the official labeller actually does

Reading `WSDMChurnLabeller.scala` (shipped with the competition data) changed two assumptions:

1. **Candidates come from the previous calendar month only.** A member is in cohort *M* only if they had a transaction in month *M − 1* whose (ordered) last expiry lands in *M*. Members on long plans (e.g. 180/365 days) with no transaction in *M − 1* are not in any official cohort. We keep this rule for label parity (P0 gate) and **report how many expiring members it excludes** as a coverage finding.
2. **Same-day transactions are ordered by a string comparison** of `plan_list_price + payment_plan_days + payment_method_id` (descending), then cancel/renew rules. This is quirky — "99…" sorts above "149…" — but changing it would break parity, so `src/data/labels.py` reproduces it exactly and a unit test pins the behaviour.

Official cohort facts (from `train.csv` / `train_v2.csv`): Feb-2017 = 992,931 members, 6.39% churn; Mar-2017 = 970,960 members, 8.99% churn; 881,701 members appear in both. The +2.6 pp month-on-month shift is direct evidence for out-of-time validation (ADR-002).

## Positive Consequences

- Every result is reported with an explicit lead time — directly usable by a retention team
- Multiple cohorts enable out-of-time validation (ADR-002) and rolling retraining
- The window sufficiency curve is itself a finding, replicating a 2026 result on a new design

## Negative Consequences

- Label reconstruction adds work and a possible error source (mitigated by the 99% gate)
- k × W grid multiplies feature builds (mitigated by building daily aggregates once in Spark)

## Implementation Notes

```python
# Point-in-time guard — enforced by tests/test_point_in_time.py
assert features.filter(F.col("event_date") >= F.col("snapshot_date")).count() == 0
```

## Related Decisions

- ADR-002: Validation strategy (depends on the cohort definition here)

## References

- Han, X. et al. (2026). How Early Is Early Enough? arXiv 2607.00473
- Mufti, M. J. et al. (2026). A Rolling-Window Framework for Churn Prediction. arXiv 2606.06776
- WSDM Cup 2018 KKBox Churn Prediction Challenge — task and label definition
