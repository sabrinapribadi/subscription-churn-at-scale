# ADR-008: Databricks Port — Asset Bundle, Unity Catalog Volumes, Serverless Job, MLflow Registry

**Status:** Accepted — gate passed on run 3 (identical to the local run); run 1 failed and is on record
**Date:** 2026-10-13
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

P1–P5 ran on one laptop: PySpark in local mode, LightGBM, MLflow on SQLite. A team would run this on a shared platform, with versioned jobs, governed data and a model registry. The PRD sets the P6 gate as *same metrics reproduced on Databricks*.

The question: **"Can the same code reproduce the champion's numbers on Databricks, and be promoted through a registry, without forking the pipeline?"**

## Decision Drivers

- One code base: local and Databricks runs must share `src/` and the scripts, with no notebook copies
- Free Edition limits: serverless compute only, a daily compute quota, outbound internet to trusted domains only, no custom storage
- Reproducible from the repo: job definition versioned next to the code
- The workspace URL and credentials stay out of the public repo
- Upload only what the champion needs (home upload speed is about 3.5 MB/s)

## Considered Options

| Option | Verdict |
|---|---|
| Notebooks copied into the workspace by hand | Rejected: forks the code; not reviewable or reproducible |
| Upload the finished feature table, train only | Rejected: would not show the PySpark pipeline running on Databricks |
| Upload all 18 GB of logs, rebuild everything | Rejected: about 90 minutes of upload and a high quota risk, for months the champion never reads |
| **Asset Bundle job: upload the champion's inputs only (about 4.3 GB), rebuild features with the same PySpark code, retrain, check parity, register** | **Chosen** |
| Download from Kaggle inside Databricks | Not possible: outbound internet is limited to trusted domains |

## Decision Outcome

- **Data:** Unity Catalog schema `workspace.churn`. Volume `raw` holds the uploaded inputs: transactions, members, listening logs for 2016-12 to 2017-03 (the 30 days before every February and March snapshot), and the official labels. It also holds the local P4 features as the parity reference. Volume `data` holds pipeline outputs.
- **Code:** `src/config.py` applies `configs/databricks.yaml` (volume paths) automatically on Databricks. `src/spark_session.py` returns the platform session there, and turns caching into a no-op, because serverless does not support caching. Nothing else changes.
- **Job** (`databricks.yml`): two serverless tasks.
  1. `build_dataset.py --months 201702 201703 --W 30` (PySpark).
  2. `databricks_train_register.py`: the P4 recipe (LightGBM, isotonic + prior shift, probability × value). It compares results with the local build, logs to MLflow and registers `workspace.churn.churn_lgbm`.
  Package versions are pinned to the local ones (LightGBM 4.7.0, scikit-learn 1.9.1, MLflow 3.17.0) on serverless environment 6 (Python 3.12.3, same as local).
- **Promotion:** the model version always registers. It gets the alias `champion` only if every check below passes.

## Gate (written before the first run)

| Check | Pass if | Local reference |
|---|---|---|
| Same population | March members and churners identical | 862,158 · 62,616 |
| Same features | No member missing on either side; ≥ 99.9% of members identical on every feature (relative 1e-6) | local `k14_wmulti`, W = 30 |
| PR-AUC | within ± 0.002 | 0.5614 |
| Churners reached in the top 10% | within ± 0.2 points | 65.33% |
| Profit, value-ordered list, central scenario | within ± 0.5% | 12,458,816 |
| Registry | the registered version reloads and scores identically | — |

The model tolerances allow for LightGBM's floating-point summation order differing across CPU counts. Data and features must match exactly.

## Results (2026-10-13)

The gate table above was committed before any Databricks run (commit `1fa327f`). Tolerances never changed. The local reference was rebuilt after the fixes below, so the same corrected code ran on both platforms.

| Run | What changed | PR-AUC local · Databricks | Profit local · Databricks | Features identical | Verdict |
|---|---|---|---|---|---|
| 1 | — | 0.5614 · 0.5670 | 12,458,816 · 12,547,119 (+0.7%) | 99.98% | **Failed** (PR-AUC, reach, profit) |
| 2 | One deterministic last-transaction row; fixed feature order | 0.5589 · 0.5606 | 12,437,811 · 12,470,605 (+0.26%) | 100% | Passed within tolerance |
| 3 | Fixed row order | **0.5594 · 0.5594** | **12,431,437 · 12,431,437** | 100% | **Passed, identical** |

**Root cause of run 1, found locally without Databricks quota.** Training the same recipe on the laptop with the Databricks-built features reproduced the Databricks numbers exactly (PR-AUC 0.5670, best iteration 208). The platform was innocent; the inputs differed:

1. **Ties in the last transaction.** `max_by` on (date, expiry) may pick any tied row, field by field. About 300 members (0.02%) got run-dependent values. Fix: one row chosen by `max` over a struct with a total order (on a tie, a cancellation wins).
2. **Column order.** The multi-window and single-window builds emit columns in different orders. LightGBM samples 80% of columns by position (`feature_fraction`), so the order changes the model (+0.002 PR-AUC on its own). Fix: features enter training in alphabetical order.
3. **Row order** (found by run 2). Spark writes rows in a platform-dependent order, and LightGBM's bagging samples rows by position. Fix: sort by cohort and member before training.

Each fix has a test: two tied rows in both orders and two partitionings; column and row order invariance.

**Registry.** `workspace.churn.churn_lgbm`: version 1 (run 1, no alias), version 2 (run 2), version 3 (run 3) holds the alias `champion`. The registered model reloads and scores identically. The `scores_march_2017` table matches the local serving artefacts: 862,158 members, 86,215 on the list, first member identical.

**Run time on serverless (run 3):** features 140 s, training and registry 150 s (46 s of it training), tables 80 s.

**Effect on earlier phases.** P4 and the serving artefacts were re-run with the deterministic pipeline (ADR-004 keeps the first-run values). Profit 12,458,816 → 12,431,437; every verdict is unchanged. P0–P3 results are records of their own phases and were not re-run.

## Consequences

- Positive: a second platform exposed three sources of nondeterminism that one laptop hid; the pipeline is now reproducible bit for bit

- Positive: the pipeline that produced every number on the page runs unchanged on a governed platform, with a versioned job and a registry
- Negative: Free Edition's daily quota caps how often the full job can run; development stays local, and Databricks runs the reproducible job
- Negative: inputs are uploaded by hand once; a production setup would land data in cloud storage directly

## Related Decisions

- ADR-001 (lead time and window), ADR-002 (out-of-time validation), ADR-004 (calibration and value ordering), ADR-005 (serving)
