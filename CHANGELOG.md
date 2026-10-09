# Changelog

Newest first. Each entry uses STAR (Situation, Task, Action, Result) so it can be told as a story.

## [0.7.1] — 2026-10-09 — Hover details on charts; "churner" wording
**Files:** docs/index.html
- **Situation:** The budget dial showed numbers only at the slider position; reading other points meant dragging. The page said "leavers", which is not the term practitioners use. The rule's curve had an unexplained kink, and the legend's "Random" swatch did not match its dashed line.
- **Task:** Let readers inspect any point directly and use industry vocabulary.
- **Action:** Added a hover tooltip on the budget dial (share reached, churner count, and churners per 100 calls for model, day-one model, rule and random) with click-to-set; hover/focus tooltips on calibration points; labelled the kink where the rule runs out of manual renewers (~12%); fixed the legend; replaced "leaver" with "churner" and defined it once.
- **Result:** Every point on the two practitioner charts is readable on hover or keyboard focus; terminology matches telecom and subscription practice.
- **Talking point:** "Practitioners should be able to point at a budget on the chart and read the answer, in their own words."

## [0.7.0] — 2026-10-09 — Practitioner view, budget dial, and an appendix of secondary metrics
**Files:** scripts/train_model.py, scripts/practitioner_report.py, data/outputs/p1_practitioner.json, docs/index.html, docs/adr/ADR-002-validation-strategy.md
- **Situation:** Results were reported in ML metrics only. Practitioners ask how many calls reach a leaver, whether it beats today's rule, and what happens on a smaller budget. A consultant recommended Gini.
- **Task:** Lead with operational answers, keep the evidence one click away, and test whether Gini would pick the right model.
- **Action:** Saved test predictions; computed capture curves, calibration, and segment cuts; added Gini, top-decile lift, H-measure, Brier, ECE, MPC and EMPC (Verbraken et al. defaults). Rebuilt the Results section as two tabs: practitioner view (four plain numbers, a budget dial, where the calls go, caveats, FAQ) and an ML appendix.
- **Result:** 48 of 100 calls reach a leaver (rule 39, random 7); +7,100 leavers a month at the same call volume; EMPC's profit-maximising share is 10.3%, matching the planned list. Found that Gini rates the realistic model below the rule while PR-AUC and top-5% capture rate it well above; scores run low (top group 37% predicted vs 48% observed); auto-renew cancellers are a third of leavers and mostly missed.
- **Talking point:** "When the consultant asked for Gini, I showed a case from our own data where Gini would have thrown away the better model — then reported it anyway, in the appendix."

## [0.6.0] — 2026-10-09 — P1 baseline: LightGBM out-of-time, three training setups
**Files:** src/features/build.py, src/data/cohorts.py, src/spark_session.py, scripts/build_dataset.py, scripts/train_model.py, tests/test_features.py, docs/index.html, docs/adr/ADR-001-task-framing.md, docs/PRD.md, data/outputs/p1_dataset.json, data/outputs/p1_baseline.json, .gitignore, .env.example
- **Situation:** Labels were settled (P0) but no model existed. The benchmark trains on February labels to predict March, yet those labels are not known when March predictions must be made.
- **Task:** Build point-in-time features at scale, train a baseline, and measure it honestly against a simple rule and against a setup a real team could run.
- **Action:** Built 30 point-in-time features for 5 monthly cohorts (~4.3M member-snapshots from 410M log rows) with a leakage test that injects post-snapshot rows. Trained LightGBM with member-level early stopping, tracked in MLflow (SQLite store). Ran three setups: benchmark (Feb official), realistic (Nov–Jan rebuilt), combined. Found and fixed Spark silently running on Java 20 instead of 17.
- **Result:** On official March labels (862,158 members, 7.26% churn, k = 14): PR-AUC 0.568 vs rule 0.342; top 10% catches 65% of churners. Realistic setup 0.505 (label-maturity cost 0.063). Rebuilt labels lowered the score (0.561) and were dropped. Payment and renewal features carry most of the signal; listening ~6%.
- **Talking point:** "The headline number is 0.568, but I also report 0.505 — what you'd get if you only trained on labels you actually have on prediction day."

## [0.5.0] — 2026-10-09 — P0 result: label gate failed, cause found, decision recorded
**Files:** src/data/cohorts.py, scripts/validate_labels.py, scripts/stream_user_logs_to_parquet.py, tests/test_cohorts_spark.py, docs/adr/ADR-001-task-framing.md, docs/adr/ADR-002-validation-strategy.md, docs/adr/README.md, docs/PRD.md, docs/index.html, data/outputs/p0_label_agreement.json
- **Situation:** The per-member Python labeller had run for 75+ minutes without finishing; the P0 gate (≥ 99% agreement with official labels) was still unanswered. The 30 GB user-log CSV would not fit on disk next to its Parquet copy.
- **Task:** Make labelling fast enough for ~20 cohorts, answer the gate honestly, and convert user logs within the disk budget.
- **Action:** Rewrote the labeller's ordering as a 4-column Spark sort with window functions and proved equivalence on 400 random histories (13/13 tests). Ran the gate: failed. Tested three hypotheses: port bug (rejected), full-history window (rejected: agreement fell), different source data (supported: 99.5% of disagreements show a real February renewal in the shipped data). Chose Option D: official labels are test truth; rebuilt labels must earn their place in training. Streamed user logs from 7z straight into month-partitioned Parquet without extracting the CSV.
- **Result:** Labelling 3.5 min instead of 75+ min. Gate failed at 98.77% (Feb) / 97.00% (Mar), with a documented cause and a testable decision instead of a quietly relaxed threshold.
- **Talking point:** "My first gate failed. I didn't move the bar. I proved my code was right, showed the benchmark labels came from different data, and turned that into a test of whether rebuilt labels help."

## [0.4.0] — 2026-10-09 — Scannable showcase layout (rule R7)
**Files:** docs/index.html
- **Situation:** Each section of the showcase opened with a 2–4 sentence paragraph; the problem statement was two paragraphs.
- **Task:** Apply portfolio rule R7: no passages, use visual structure.
- **Action:** Problem became a before/after flow plus three numbered needs; each method became 3 numbered steps or bullets plus a one-line "why it matters"; added a clickable pipeline flowchart (labels → snapshot → validation → model → call list); "Our take" became two bullet lists; the table key became a tag legend.
- **Result:** Longest paragraph on the page dropped from 42 to 22 words; all simulations and formulas unchanged.
- **Talking point:** "The page went from essay to dashboard: a reader can follow the method by scanning the steps and the flow."

## [0.3.1] — 2026-10-09 — Explicit status labels in the alternatives table
**Files:** docs/index.html
- **Situation:** The "Why this methodology" table marked rejected options with strikethrough. A first reader did not know what it meant, and it was inconsistent: options kept as baselines looked the same as unmarked rejected ones.
- **Task:** Make each alternative's fate readable without explanation.
- **Action:** Replaced strikethrough with labelled tags (rejected, baseline, secondary, deferred, reference only) and added a one-line key under the table.
- **Result:** Every alternative now states its role; "sort by probability" and "RFM only" read correctly as baselines the chosen methods must beat.
- **Talking point:** "A rejected option and a baseline are different things, so the page says which is which."

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
