# ADR-008: Databricks Port — Asset Bundle, Unity Catalog Volumes, Serverless Job, MLflow Registry

**Status:** Proposed — gate written before the first Databricks run
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

## Results

Pending the first run.

## Consequences

- Positive: the pipeline that produced every number on the page runs unchanged on a governed platform, with a versioned job and a registry
- Negative: Free Edition's daily quota caps how often the full job can run; development stays local, and Databricks runs the reproducible job
- Negative: inputs are uploaded by hand once; a production setup would land data in cloud storage directly

## Related Decisions

- ADR-001 (lead time and window), ADR-002 (out-of-time validation), ADR-004 (calibration and value ordering), ADR-005 (serving)
