PRODUCT REQUIREMENT DOCUMENT (PRD)
Project: Subscription Churn at Scale — Who Leaves, When, Why, and Who to Call First
Version: 1.0 (P6: Databricks port reproduces the champion exactly; planner agent; technical walkthrough page)
Author: Sabrina Pribadi
Date: October 9, 2026
Status: Active — P0–P6 complete (P0, P3, P4 gates failed, documented; P6 passed on run 3); P7 next


1. EXECUTIVE SUMMARY

Problem: A subscription business usually learns that a customer has left only after the
renewal date has passed. By then the retention team has nothing to act on. Public
competition framings of this problem (WSDM Cup 2018) predict churn *at* the expiry date,
which is too late to intervene. Retention teams need a short, ranked list of at-risk
customers *days before* expiry, ordered by how much revenue is at stake, with a reason
they can act on.

Solution: A Spark-based pipeline over ~400M rows of daily usage logs that builds
point-in-time customer snapshots k days before each membership expiry; a gradient-boosted
churn model augmented with self-supervised behavioural embeddings; a LambdaMART ranker
that orders customers by revenue-at-risk; and a set of small services (features, scoring,
LLM explanation, MCP gateway) so the model can be called by apps and AI agents.

Value Proposition: Turn a leaderboard-style churn classifier into an operational retention
tool — with honest out-of-time evaluation, measured lead time, and a ranked list judged by
profit captured in the top k, not by AUC alone.

Success Metrics (pre-registered — see ADR-002):
- Label reconstruction agrees with the official WSDM labels on ≥ 99% of overlapping members
- Out-of-time PR-AUC reported for every phase, on a later expiry cohort than training
- Behavioural embeddings gate: PR-AUC(GBM + embeddings) ≥ PR-AUC(GBM only) + 0.02
- Ranking gate: LambdaMART profit@top-10% > sort-by-probability profit@top-10%
- Every service has a pydantic contract, a health check, and a contract test in CI
- Showcase page (docs/index.html) follows Problem → Why → Methodology → Results → Our take


2. PROJECT CONTEXT AND BACKGROUND

This project demonstrates:

1. Data engineering at scale: PySpark ETL over ~400M daily-log rows; point-in-time
   correctness (no feature may use data after the snapshot date); Delta/Parquet outputs;
   runs locally and on Databricks Free Edition.
2. Temporal problem framing: prediction made k days before expiry (k ∈ {7, 14, 30});
   observation window W tested rather than assumed, following evidence that window
   sufficiency is design-dependent (arXiv 2607.00473, 2026).
3. Deep behavioural understanding: a self-supervised sequence encoder over daily usage
   produces behavioural embeddings, used for personas and as model features — tested as
   an ablation, not assumed to help.
4. Ranking: LambdaMART (LightGBM lambdarank) optimising a revenue-at-risk ordering,
   evaluated by NDCG@k and profit@k.
5. Microservices and modular GenAI: four FastAPI services with typed contracts; a GenAI
   module with a provider interface (OpenAI default), versioned prompts, and a single tool
   registry shared by the agent and the MCP server.
6. MLOps: MLflow tracking and model registry; CI with lint, type checks, tests.

Data Source: WSDM Cup 2018 — KKBox Churn Prediction Challenge (Kaggle).
- members: demographics and registration channel per member (msno)
- transactions: payment plan, price, auto-renew, cancel flag, transaction and expiry dates
- user_logs: one row per member per day — counts of songs played to <25%, 25–50%,
  50–75%, 75–98.5%, >98.5% of length; unique songs; total seconds
- train / train_v2: official churn labels for Feb-2017 and Mar-2017 expiry cohorts
- Churn definition (official): no new valid subscription within 30 days after expiry


3. SCOPE

In-Scope:
- Spark ETL and label reconstruction for multiple monthly expiry cohorts
- Point-in-time snapshots at k ∈ {7, 14, 30} days before expiry
- Observation-window sufficiency curve for W ∈ {30, 60, 90, 120, 180} days
- Baseline: GBM on hand-crafted RFM, payment and engagement features
- Deep behaviour: self-supervised encoder → embeddings → personas + features (ablation)
- Ranking: LambdaMART on revenue-at-risk relevance labels
- Services: feature-svc, scoring-svc, explain-svc, mcp-gateway (docker-compose)
- GenAI: provider interface, prompt registry, tool registry, offline eval set
- MLflow tracking + registry; GitHub Actions CI
- Showcase page and Streamlit dashboard reading pre-computed outputs

Out-of-Scope (this project; see CHN-2):
- Causal uplift and offer optimisation (which customers are persuadable, what to offer)
- Real-time streaming features
- Any non-public data


4. USER PERSONAS AND STORIES

| Persona                   | Goal                                                         | Pain Point                                     |
|---------------------------|--------------------------------------------------------------|------------------------------------------------|
| Rina (Retention Lead)     | A daily call list of 500 members most worth saving          | Current lists are sorted by churn probability, not value |
| Budi (CRM Agent)          | Know *why* a member is at risk before calling               | Scores have no explanation                     |
| Maya (Data Scientist)     | Know how much history the model really needs                | Window length is chosen by habit               |
| Arif (ML Engineer)        | Call scoring from apps and AI agents with a stable contract | Models are notebooks, not services             |
| Lena (Finance Partner)    | See revenue protected per 1,000 contacts                    | Model metrics don't translate to money         |

User Stories:
- As a retention lead, I can request the top-k members by revenue-at-risk for next week's expiries.
- As a CRM agent, I can ask in plain English why a member is at risk and get a grounded answer.
- As a data scientist, I can see the PR-AUC vs observation-window curve for each design.
- As an ML engineer, I can call /members/{id}/score and /members/{id}/explanation with typed requests and get versioned responses.
- As an AI agent (via MCP), I can call member_risk(id), why_at_risk(id), call_list(share) and what_if(save_rate, cost).
- As a retention manager, I can ask a planning question in plain words (POST /ask) and get an answer whose numbers come from the tools.


5. FUNCTIONAL REQUIREMENTS

Module A: Data & Labels — defined in ADR-001
Module B: Features (RFM, payment, engagement, trend) — Phase 1
Module C: Behavioural encoder — Phase 3 (ADR-003)
Module D: Ranking and calibration — Phase 4 (ADR-004)
Module E: Services, GenAI notes and planner agent — Phase 5 (ADR-005, ADR-006, ADR-007)
Module F: Databricks port & MLflow registry — Phase 6 (ADR-008)


7. DATA STRATEGY

- Raw data stored outside the repo and outside cloud-synced folders: ~/data/kkbox/raw
- Converted once to partitioned Parquet (by month) for Spark
- Only small, aggregated outputs (metrics JSON, sample predictions) are committed
- Split: by expiry cohort (out-of-time) — never random rows (ADR-002)


9. IMPLEMENTATION PLAN

| Phase | Goal                                              | Gate / exit criterion                                        |
|-------|---------------------------------------------------|--------------------------------------------------------------|
| P0    | Spark ETL + label reconstruction                  | ≥ 99% agreement with official labels on overlapping members  |
| P1    | GBM baseline, k = 14, W = 120                     | Out-of-time PR-AUC reported; leakage tests pass              |
| P2    | Observation-window sufficiency curve              | Curve + knee reported per k                                  |
| P3    | Behavioural embeddings ablation                   | PR-AUC gain ≥ +0.02 out-of-time (else documented as negative)|
| P4    | LambdaMART revenue-at-risk ranking                | profit@10% > sort-by-probability                             |
| P5    | Microservices + GenAI module + MCP                | Contract tests + LLM eval set pass in CI                     |
| P6    | Databricks Free Edition port + MLflow registry    | Same metrics reproduced on Databricks                        |
| P7    | Operate monthly: dashboard, drift check, held-out agent questions | ADR-009 gates G1–G4 (page published: already met in P1)      |


11. RISKS AND MITIGATIONS

| Risk                                                   | Mitigation                                                  |
|--------------------------------------------------------|-------------------------------------------------------------|
| Full user_logs (~30 GB CSV) strains a laptop           | Convert to Parquet once; develop on a 10% member sample     |
| Known quirks in official labels / transactions         | Reconstruct labels from transactions; report disagreements  |
| Leakage via transactions after the snapshot date       | Point-in-time joins + a unit test that fails on future dates|
| Databricks Free Edition daily quota                    | Develop locally; run final reproducible jobs on Databricks  |
| Embeddings add complexity without gain                 | Pre-registered gate; negative result reported if it fails   |


14. APPENDIX — References

- WSDM Cup 2018 KKBox Churn Prediction Challenge (Kaggle)
- Predicting Customer Churn: Extreme Gradient Boosting with Temporal Data (2018). arXiv 1802.03396
- Han, X. et al. (2026). How Early Is Early Enough? Design-Dependent Observation-Window Sufficiency in Subscription Churn Prediction. arXiv 2607.00473
- Mufti, M. J. et al. (2026). A Rolling-Window Framework for Churn Prediction and Behavioral Driver Identification. arXiv 2606.06776
- Exploiting time-varying RFM measures for customer churn prediction with deep neural networks. Annals of Operations Research (2023). doi:10.1007/s10479-023-05259-9
- Causal Customer Churn Analysis with Low-rank Tensor Block Hazard Model. arXiv 2405.11377
