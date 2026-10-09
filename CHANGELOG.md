# Changelog

Newest first. Each entry uses STAR (Situation, Task, Action, Result) so it can be told as a story.

## [0.3.0] — 2026-10-09 — Showcase page with interactive method simulations
**Files:** docs/index.html
- **Situation:** The methodology lived in ADRs and code. A hiring manager or interviewer would need to read Markdown and Python to understand why each choice was made.
- **Task:** One self-contained HTML page, uploadable anywhere, that walks Problem → Why this methodology → Methodology → Results → Our take, and lets a reader move each method's logic and math by hand.
- **Action:** Built `docs/index.html` with nine in-browser simulations on synthetic data: the official churn label rule, point-in-time snapshots, window sufficiency, out-of-time vs random split, PR-AUC vs ROC-AUC under imbalance, gradient boosting, behavioural embeddings (linear case = PCA), profit@k, and LambdaMART λ-gradients. Every method shows its formula and its status (in use / decided / planned). No server, no data files; fonts fall back to system faces offline. Results section shows the pre-registered gates and marks P0 as running.
- **Result:** One file (~65 KB) that works from disk, GitHub Pages, or a shared link. The PR-AUC simulation reproduces the analytic result that ROC-AUC stays at 0.839 while PR-AUC falls from 0.834 to 0.341 when churn drops from 50% to 6.4%.
- **Talking point:** "Instead of telling interviewers why I chose PR-AUC, I let them drag the churn rate and watch ROC-AUC stay flat while the call list fills with false alarms."

## [0.2.0] — 2026-10-09 — Label reconstruction ported from the official labeller
**Files:** src/data/labels.py, src/data/cohorts.py, src/spark_session.py, scripts/convert_to_parquet.py, tests/test_labels.py, tests/test_cohorts_spark.py, docs/adr/ADR-001-task-framing.md
- **Situation:** ADR-001 needs labels for more cohorts than the two official months, validated at >= 99% agreement. The competition ships its labeller as Scala source, with undocumented ordering rules.
- **Task:** Reproduce the official labels exactly, at Spark scale, so new cohorts can be trusted.
- **Action:** Read the Scala labeller line by line and ported it to a pure-Python core (testable without Spark) plus a Spark `applyInPandas` wrapper. Kept its quirks for parity — history is the previous month only, and same-day transactions sort by a string signature. Wrote 10 unit tests (one per rule in the Scala comments) and a Spark end-to-end test. Moved to PySpark 4.0 (matches Databricks serverless; 3.5 fails on Python 3.12). Raw data kept in ~/data/kkbox, outside cloud sync.
- **Result:** 12/12 tests pass. Official cohorts profiled: Feb-2017 6.39% churn, Mar-2017 8.99%, 881,701 members in both — a 2.6 pp shift that justifies out-of-time testing. Agreement gate not yet run (waiting for the 7 GB user_logs download).
- **Talking point:** "I didn't guess the label definition — I ported the organiser's own labeller, quirks included, and unit-tested every rule before touching a model."

## [0.1.0] — 2026-10-09 — Project design: framing, validation, phases
**Files:** README.md, docs/PRD.md, docs/adr/README.md, docs/adr/ADR-001-task-framing.md, docs/adr/ADR-002-validation-strategy.md, configs/default_config.yaml, Makefile, .gitignore, .env.example
- **Situation:** The best-known public churn benchmark (WSDM Cup 2018) predicts churn at the expiry date, ranks by probability, and is usually evaluated on random splits — none of which match how a retention team works.
- **Task:** Design a churn system that predicts early enough to act, is evaluated on future cohorts, and ranks by money at stake — with every success criterion fixed before training.
- **Action:** Reframed the task as point-in-time snapshots k days before expiry (ADR-001), grounded in two 2026 papers showing temporal framing and window length matter more than model choice. Chose out-of-time cohort validation with PR-AUC and profit@top-10% (ADR-002). Defined 8 phases, each with a falsifiable gate. Rejected: competition framing (zero lead time), random splits (leakage), accuracy/ROC-AUC as primary (imbalance).
- **Result:** Design complete; 2 ADRs, PRD v0.1, 4 pre-registered gates. No data processed yet.
- **Talking point:** "Before modelling, I changed the question: not 'will they churn?' but 'who should we call two weeks before renewal, and in what order?'"
