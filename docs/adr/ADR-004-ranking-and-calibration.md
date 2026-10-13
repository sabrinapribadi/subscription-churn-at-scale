# ADR-004: Call-List Ranking and Calibration — Probability vs Expected Value vs LambdaMART

**Status:** Accepted — G1 and G2 failed; expected-value sort adopted under the decision rule
**Date:** 2026-10-12
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

The P2 model (k = 14, W = 30) orders members by churn probability. Two problems remain:

1. **Scores run low.** Trained on February (5.5% churn), scored on March (7.3%): the top group was predicted at 37% and churned at 48%. If scores drive offers or budgets, "30%" must mean 30%.
2. **Probability is not value.** Members pay 99–149 a month (annualised ≈ 1,200–1,825; some yearly plans more), and churners are worth more on average (median 1,813 vs 1,570). Two members with the same probability are not worth the same call.

The question: **"Which ordering of the call list protects the most money for the same number of calls — and are the scores honest?"**

## Decision Drivers

- Calibration must work on prediction day: March labels are not known when March is scored
- If probabilities are calibrated, sorting by expected value (probability × value) is already the expected-profit optimum — a learned ranker must beat that, not just the probability sort
- Profit depends on assumptions (save rate, contact cost); results must hold across a sensitivity grid

## Considered Options

**Calibration**

| Option | Evidence | Verdict |
|--------|----------|---------|
| None (raw LightGBM) | — | Baseline |
| Isotonic regression on a February hold-out | Standard post-hoc calibration | Fixes shape, not the month-to-month churn shift |
| **Isotonic + prior-shift EM on unlabelled March scores** | Saerens, Latinne & Decaestecker (2002), *Neural Computation* 14(1); "hard to beat" with bias-corrected calibration — Alexandari et al. (2020), ICML, arXiv 1901.06852 | **Chosen** — re-estimates March's churn rate from scores alone |
| Recalibrate on the latest labelled month | — | Rejected: labels mature ~30 days after expiry (P1 label-maturity finding) |

**Ranking**

| Option | Evidence | Verdict |
|--------|----------|---------|
| Sort by calibrated probability | P1–P3 practice | Baseline (pre-registered comparator) |
| **Sort by expected value: calibrated p × annual value** | Expected-profit optimum when p is calibrated; Verbeke et al. (2012), EJOR | Strong simple baseline |
| **LambdaMART** (LightGBM `lambdarank`) | Burges (2010), *From RankNet to LambdaRank to LambdaMART*, MSR-TR-2010-82 | Candidate |
| Uplift-based targeting | Ascarza (2018), JMR; Devriendt et al., Information Sciences | Deferred to CHN-2 (needs treatment data) |

## Decision Outcome

- **Member value** r = amount paid per day of the last plan × 365 (12 months of revenue if retained; list price per day when paid = 0).
- **Calibration:** isotonic regression fitted on the February early-stopping hold-out (10% of members, grouped by member); then Saerens EM on March's unlabelled calibrated scores, starting from the February training churn rate.
- **LambdaMART:** February training members shuffled into query groups of 1,000; relevance 0 for non-churners, 1–3 for churners by value tercile; early stopping on NDCG@100 of hold-out groups; features = P2 features + r.
- **Profit at the top k:** Π(k) = Σ over called members (s · y · r − c). Central case s = 0.20, c = 20; sensitivity grid s ∈ {0.10, 0.20, 0.30} × c ∈ {0, 20, 50}.

**Pre-registered gates**

| # | Gate | Source |
|---|------|--------|
| G1 | Profit@10%(LambdaMART) > profit@10%(probability sort), central case | ADR-002 P4 gate |
| G2 | Expected calibration error on March ≤ 0.010 after calibration (P1: 0.016) | New, practitioner request |

**Decision rule:** if expected-value sort ≥ LambdaMART on profit@10% (central case), recommend the expected-value sort — it is simpler and needs no extra model.

**Falsification conditions:**

| Result | Diagnosis | Next action |
|--------|-----------|-------------|
| LambdaMART ≤ probability sort | Value differences too small or ranker under-fits | Report; keep probability or EV sort |
| EV sort ≥ LambdaMART > probability sort | Value matters, but the closed-form rule captures it | Ship EV sort; LambdaMART stays a documented experiment |
| LambdaMART > EV sort across the grid | Interactions between risk and value the product misses | Ship LambdaMART; add to serving (P5) |
| ECE not reduced below 0.010 | Shift is not purely in the churn rate | Report; add monthly recalibration on matured labels as a lagged check |

## Results (2026-10-12; re-run 2026-10-13)

*Re-run on 13 Oct with the deterministic pipeline from ADR-008 (one last-transaction row on ties, fixed feature order, fixed row order). First-run values are kept in brackets. No verdict changed.*

**Ranking** — Mar-2017, top 10% (86,215 calls), central case s = 0.20, c = 20:

| Order | Profit / month | Churners reached | Value at risk reached |
|---|---|---|---|
| probability | 12,408,456 (12,445,531) | 65.2% | 65.5% |
| expected_value | 12,431,437 (12,458,816) | 64.4% | 65.6% |
| lambdamart | 9,699,163 (9,731,189) | 48.9% | 53.0% |

Expected-value sort wins **9 of 9** grid scenarios, by 0.2–0.4% (first run: ~0.1%; plans are priced 99–149, so value barely reorders the list). LambdaMART loses all 9 (−22% at the central case, as in the first run): NDCG with exponential gains concentrates the top of each group on top-tier churners and drops lower-value ones. Not tuned further — that would be chasing a failed gate.

**Calibration** — ECE raw 0.0156 → isotonic 0.0156 → + EM 0.0120 (first run: 0.0158 → 0.0158 → 0.0128). EM estimated March churn at 6.06% (first run 5.98%; actual 7.26%; Feb training 5.55%).

**Verdicts:** G1 failed (LambdaMART < probability sort). G2 failed (0.0120 > 0.010). Falsification rows: "LambdaMART ≤ probability sort → keep probability or EV sort" and "ECE not below 0.010 → shift is not purely in the churn rate; add a lagged monthly recalibration on matured labels". **Adopted:** expected-value sort with isotonic + EM scores; ties broken by the raw score (isotonic is a step function).

## Consequences

- Positive: profit, not AUC, decides the call list; scores become usable for budgeting
- Negative: profit depends on assumed save rate and contact cost — shown as a grid, not a single number

## References

- Saerens, Latinne & Decaestecker (2002). Adjusting the outputs of a classifier to new a priori probabilities. *Neural Computation* 14(1)
- Alexandari, Kundaje & Shrikumar (2020). Maximum Likelihood with Bias-Corrected Calibration is Hard-To-Beat at Label Shift Adaptation. ICML — arXiv 1901.06852
- Burges (2010). From RankNet to LambdaRank to LambdaMART: An Overview. Microsoft Research MSR-TR-2010-82
- Verbeke et al. (2012). New insights into churn prediction in the telecommunication sector: a profit driven data mining approach. *EJOR* 218(1)
- Ascarza (2018). Retention Futility. *Journal of Marketing Research* 55(1)
