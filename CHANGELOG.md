# Changelog

Newest first. Each entry uses STAR (Situation, Task, Action, Result) so it can be told as a story.

## [0.13.1] — 2026-10-12 — CI green: the P5 gate, verified
**Files:** .github/workflows/ci.yml, src/gateway/mcp_server.py, docs/adr/ADR-005-service-boundaries.md, docs/index.html, README.md
- **Situation:** The first CI run failed before any test ran: pip caching looked for a requirements.txt/pyproject.toml the repo does not have. The ADR already said "passed".
- **Task:** Make the gate real and make the record match it.
- **Action:** Keyed the pip cache on the CI requirement files and moved to current action versions (Node 20 deprecation). Linked the passing run in ADR-005; corrected the page's test count to what CI runs; made a docstring vendor-neutral; added a CI badge.
- **Result:** [Run 38279575714](https://github.com/sabrinapribadi/subscription-churn-at-scale/actions/runs/38279575714): tests 55 passed, 1 skipped (PyTorch, local-only); evaluation set 100% grounded; Docker image built.
- **Talking point:** "I don't call a gate passed until CI shows it — and when my first run failed on setup, the record says so."

## [0.13.0] — 2026-10-12 — P5: services, grounded GenAI notes, MCP gateway, CI
**Files:** src/services/ (contracts, store, clients, apps, artifacts), src/genai/ (providers, prompts, grader, explain, tools, dictionary), src/gateway/mcp_server.py, src/features/schema.py, scripts/export_serving_artifacts.py, scripts/llm_eval.py, tests/ (conftest, test_services, test_genai, test_gateway, llm_eval/cases.json, test_behaviour), Dockerfile, docker-compose.yml, requirements-serving.txt, requirements-ci.txt, .github/workflows/ci.yml, Makefile, configs/default_config.yaml, docs/adr/ADR-005, ADR-006, docs/index.html, README.md, docs/PRD.md
- **Situation:** The model and call list lived in batch scripts. CRM screens and AI assistants need the same answers on demand, and a language model explaining a score can invent reasons, cost money, and be slow.
- **Task:** Serve scores, reasons and call lists behind typed contracts; let AI assistants use them through MCP; make plain-language notes provably faithful; know their cost and latency (rule R13); gate it all in CI.
- **Action:** Four services (features, scoring, explanation, MCP gateway) from one image; pydantic contracts; Local and HTTP clients with one interface. GenAI module: template and OpenAI providers with per-call metering, a versioned prompt, a rule-based grader (numbers, reasons, no demographics, length, fixed action list) with template fallback, and a cache checked before any expensive work. One tool registry served over MCP and exportable as OpenAI function schemas. Researched current methods (Explingo narrator + grader; 2026 evidence that fluent notes act as trust heuristics) and official OpenAI prices. Found and fixed: cache checked too late (37 ms → 0.13 ms), a rounding off-by-one in call counts, Spark leaking into the serving image, MCP SDK 2.x API changes.
- **Result:** Serving reproduces P4 exactly (12,458,816). Real end-to-end over HTTP: 80 ms first answer, 7 ms repeat. 56/56 tests; 12/12 evaluation cases grounded with correct actions; ≈ $0.10 per 1,000 AI notes estimated; no API key needed in CI. Page: assistant example in the Solution section, serving deep dive with budgets; collapsed page 7.1 screens.
- **Talking point:** "The AI note can't say anything the model didn't: every number and reason is checked, and if the LLM improvises, the agent gets the safe template — at about ten cents per thousand notes."

## [0.12.1] — 2026-10-12 — Full test suite runs in one command again
**Files:** tests/test_behaviour.py
- **Situation:** After P4 added LightGBM-based tests, running the whole suite segfaulted: the autoencoder test loads PyTorch in the same process, and on macOS their OpenMP runtimes clash (the issue already handled in the P3 pipeline).
- **Task:** Keep every test in the default `pytest` run without the crash.
- **Action:** The PyTorch test now runs in a child process and checks its result.
- **Result:** 25/25 tests pass in one `pytest tests/` run.
- **Talking point:** "When two native libraries can't share a process, the test isolates them the same way production does."

## [0.12.0] — 2026-10-12 — Hiring-team-first page; cost-scenario picker
**Files:** docs/index.html, src/models/ranking.py, scripts/rank_and_calibrate.py, data/outputs/p4_rank_calibrate.json, tests/browser/hover_test.js, tests/browser/controls_test.js, Makefile
- **Situation:** The page showed everything at once (~19 screens). Reviewers asked what the "9 cost scenarios" were, and the answer was buried in an appendix table with absolute numbers only.
- **Task:** Let a hiring team grasp data, problem, approach and solution in about two minutes, and make the cost assumptions explorable rather than asserted.
- **Action:** Rebuilt the page around rule R12: glance strip (data · problem · approach · result), then Problem, a new Data section (410.5M logs, 23.0M transactions, 6.8M members, label, test design), a new Approach section (pipeline + "tried vs chose + deciding number"), Solution for practitioners, Our take; simulations, decision log, extra findings and technical appendix moved into collapsible sections that links open automatically. Added a save-rate × call-cost picker (presets: pessimistic, central, optimistic) driven by exported value-by-budget curves that reproduce all 27 scenario-table cells exactly; the scenario table gained a plain-language note and relative-difference columns. Fixed a phone overflow from grid children that would not shrink.
- **Result:** Collapsed page ~7 screens (from 19). 47/47 control checks (including picker = table in all presets, links open collapsed sections) and 48/48 tooltip checks pass; no sideways scroll at 400, 768 or 1280 px, collapsed or open; no JS errors.
- **Talking point:** "When someone asks 'what are the cost scenarios?', I hand them the sliders: any save rate and call cost, and the best number of members to call — and the ranking of methods never changes."

## [0.11.3] — 2026-10-12 — Full audit of the published page: numbers, controls, links, sources
**Files:** docs/index.html, tests/browser/controls_test.js, Makefile
- **Situation:** The page had grown over five phases; it needed a check that every number is right, every control works, and nothing is stale on either the artifact or GitHub Pages.
- **Task:** Audit content and behaviour end to end, the way a reviewer would.
- **Action:** Confirmed the artifact body and the live Pages file are byte-identical to the repo. Checked 36 numeric claims against the result files (all match). Exercised every control in Chrome (15 sliders, 2 checkboxes, 6 buttons, click-to-set, tabs by mouse and keyboard, 7 FAQs, 10 in-page links) and every external link. Fixed: the "Feb 2017 · 6.4%" preset showed 6.5% (slider step 0.005 → 0.001); a P2 claim ("within 0.3 points") that was true for PR-AUC but not churners reached; stale status tags (3.2–3.6), a Why-table row still naming LambdaMART as the chosen order, record count (~410M), date, and a leakage-test count; added the real profit peak to the FAQ and 10 primary sources used on the page. Added the control audit to the repo.
- **Result:** 36/36 numbers match; 37/37 control checks and 48/48 tooltip checks pass; all external links resolve; no JS errors.
- **Talking point:** "Before calling the page done, I audited it like a reviewer: every number traced to its result file, every button clicked by a test."

## [0.11.2] — 2026-10-12 — Every tooltip checked on desktop (light and dark) and phone
**Files:** docs/index.html, tests/browser/hover_test.js, Makefile
- **Situation:** After the hide fix, a full visual review found long values overlapping their labels, an 8-row persona tooltip, tooltips covering 72–128% of the chart on phones, a wrong year ("Nov 2017" for Nov 2016), and a chart label running into the next zone.
- **Task:** Check every tooltip the way a reader sees it, on the artifact build and on GitHub Pages, in desktop light, desktop dark, and phone width.
- **Action:** Tooltip rows now keep the label whole and wrap the value; phones show details as a panel under the chart; persona tooltip cut to 6 rows; dates computed with their real year; shortened the grace-zone label. Extended the Chrome test to three modes with screenshots of every tooltip.
- **Result:** 48/48 checks pass (16 tooltips × 3 modes) on both the artifact build and the Pages file: shown on hover, inside the chart or under it on phones, hidden on leave; none on load; no sideways scroll; no JS errors.
- **Talking point:** "I test charts the way readers see them — light, dark, and on a phone — and screenshot every tooltip before publishing."

## [0.11.1] — 2026-10-12 — Tooltips that hide, stay small, and stay out of the way
**Files:** docs/index.html, tests/browser/hover_test.js, Makefile, .gitignore
- **Situation:** On GitHub Pages, tooltips stayed on screen after the pointer left and covered the charts; the appendix tab was also always visible. The artifact preview hid the bug because it adds a global "hidden" reset.
- **Task:** Make tooltips appear only while hovering, keep them small and inside the chart, and catch this class of bug before publishing.
- **Action:** Added an explicit `[hidden]` rule (component `display` styles were overriding it); shrank tooltips and placed them in the quadrant away from the cursor, clamped inside the chart; hide all tips on scroll, window blur, leaving the page, or tapping elsewhere; fixed the LambdaMART row tooltip (its container was created during the first hover, which fired an immediate "leave"). Added a real-Chrome test (puppeteer) that hovers every chart, checks the tooltip is inside it, then checks it disappears — the earlier jsdom test could not see CSS.
- **Result:** 15/15 charts and the ranking rows pass in Chrome: visible on hover, inside the chart, hidden after leaving; no tooltips on load; appendix hidden until clicked. Budget-dial tooltip 246 → 176 px tall.
- **Talking point:** "My first hover test passed while users saw broken tooltips — it couldn't see CSS. I replaced it with a real-browser test that checks what a person actually sees."

## [0.11.0] — 2026-10-12 — P4: call list ordered by money at stake; honest look at calibration
**Files:** src/models/ranking.py, src/models/baseline.py, scripts/rank_and_calibrate.py, tests/test_ranking.py, configs/default_config.yaml, docs/adr/ADR-004-ranking-and-calibration.md, docs/adr/README.md, docs/index.html, docs/PRD.md, README.md, data/outputs/p4_rank_calibrate.json
- **Situation:** Scores ran low (top group predicted 37%, observed 48%) because March churned more than February; the list ignored that members are worth different amounts.
- **Task:** Make scores usable on prediction day without March labels, and find the call-list order that protects the most money — judged on profit, with the gates set first.
- **Action:** Isotonic calibration plus Saerens prior-shift EM on unlabelled March scores; member value = paid per day × 365; compared probability sort, probability × value, and LambdaMART across 9 save-rate × call-cost scenarios. Fixed a tie-ordering flaw (isotonic steps) by breaking ties with the raw score. Added a hoverable profit chart and appendix tables.
- **Result:** Top-10% list protects ≈12.5M a month (66% of value at risk). Probability × value wins 9/9 scenarios but by only 0.1%; LambdaMART loses 22% (G1 failed). Calibration error 0.0158 → 0.0128, short of 0.010 (G2 failed): EM recovered only part of the churn shift.
- **Talking point:** "The fancy ranker lost 22% of the money; the one-line rule — probability times value — won every scenario. I shipped the rule and wrote down why."

## [0.10.0] — 2026-10-12 — P3: listening shape adds no signal; five personas for practitioners
**Files:** scripts/build_sequences.py, scripts/behaviour_ablation.py, src/models/behaviour.py, tests/test_behaviour.py, docs/adr/ADR-003-behaviour-encoder.md, docs/adr/README.md, docs/index.html, docs/PRD.md, README.md, data/outputs/p3_behaviour.json
- **Situation:** A third of churners are auto-renew members who cancel; the list reached only 1 in 4. Their payment record looks safe, so the hope was that changes in listening would warn earlier.
- **Task:** Test, against a +0.02 PR-AUC bar set in advance, whether listening shape adds signal — comparing a cheap option with two learned ones.
- **Action:** Extracted 60-day daily sequences (≈22M member-days per month); built three arms on top of the P2 model: hand-crafted shape statistics, a self-supervised masked autoencoder (labels never used), and frozen Mantis-8M embeddings (100k sample per month, every arm re-scored on the same sample). Fixed two macOS issues on the way (LightGBM/PyTorch OpenMP crash; Arrow/PyTorch deadlock) by staging the job. Clustered members into five personas and added a hoverable persona chart.
- **Result:** Gate failed for every arm (best +0.004, within noise); no gain on auto-renew cancellers. Personas give practitioners messaging angles: silent payers (20% of members, list reaches 36% of their churners) and re-engaging long-time members (highest churn, 11%).
- **Talking point:** "I tested a hand-crafted baseline, a self-supervised encoder and a 2025 foundation model on the same split. None beat the bar, so I shipped none of them to scoring — and turned the work into personas the CRM team can use."

## [0.9.1] — 2026-10-12 — MIT license
**Files:** LICENSE
- **Situation:** The repository had no license file, so by default nobody else could legally reuse the code.
- **Task:** Make the portfolio code reusable with credit, consistently across all portfolio repositories.
- **Action:** Added the standard MIT license (© 2026 Sabrina Pribadi). Data sources keep their own terms; the license covers code only.
- **Result:** GitHub now detects the license as MIT; no code changed.
- **Talking point:** "All my portfolio code is MIT-licensed, so anyone can reuse it with attribution."

## [0.9.0] — 2026-10-09 — P2: how early can we call, how much history do we need
**Files:** src/features/build.py, src/models/baseline.py, src/evaluation/metrics.py, scripts/build_dataset.py, scripts/train_model.py, scripts/window_curve.py, tests/test_features.py, configs/default_config.yaml, docs/index.html, docs/adr/ADR-001-task-framing.md, docs/PRD.md, README.md, data/outputs/p2_dataset.json, data/outputs/p2_window_curve.json
- **Situation:** P1 used a 14-day lead time and 120 days of history by assumption. A 2026 study on this dataset found the history "knee" anywhere from 30 to 120 days depending on design.
- **Task:** Measure both choices on real data — 4 lead times × 5 history windows — without 40 separate 20-minute feature builds.
- **Action:** Computed all five windows in one pass over 410M log rows (equivalence test vs P1 features); moved model and metric code into src/ and confirmed P1 reproduces to 0.0 difference; trained 20 models (Feb → Mar); added two hoverable practitioner charts and the full grid to the appendix; rewrote the README in practitioner-first style.
- **Result:** Lead time is the real trade-off: churners reached at a 10% call budget fall from 68% (7 days) to 65% (14) to 60% (30) — about 3,600 fewer a month from 14 to 30 days. History length is not: 30 to 180 days all within 0.003 PR-AUC, the same as run-to-run noise → use 30 days. Both outcomes match pre-registered falsification rows in ADR-001.
- **Talking point:** "I measured my own noise floor — same features, different column order, 0.003 PR-AUC — and used it to show that 180 days of history buys nothing over 30, while each extra week of warning costs real churners."

## [0.8.0] — 2026-10-09 — Hover details on every chart; plain-language NDCG
**Files:** docs/index.html
- **Situation:** Readers could not read exact values off most charts; "NDCG" and the rule's kink ("runs out of manual renewers") were unexplained; the calibration labels overlapped the reference line.
- **Task:** Apply rule R10 to all charts and explain the jargon in words.
- **Action:** Added one shared hover helper (tooltip + highlight ring) and wired it into all 10 SVG charts, plus row tooltips on the LambdaMART table (tier, score, push, rank weight, and why the member is pushed up or down). Rewrote NDCG as "how close the top 5 is to the best possible top 5", with the rank weights spelled out. Replaced the kink label with "12%: every manual renewer has been called — rule moves on to auto-renew members (about 3% churn)". Moved the calibration labels off the line. Verified with a headless DOM test that hovers every chart.
- **Result:** 12 charts with tooltips; 0 runtime errors; the readout now says "NDCG@5 = 0.911: the top 5 is worth 91% of a perfect top 5".
- **Talking point:** "Every chart answers 'what am I looking at?' on hover, and the test suite checks it."

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
