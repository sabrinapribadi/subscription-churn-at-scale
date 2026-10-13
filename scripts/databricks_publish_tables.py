"""P6 task 3: publish results as Unity Catalog tables for browsing and SQL (ADR-008).

    workspace.churn.features_k14_w30   point-in-time features, February and March 2017
    workspace.churn.scores_march_2017  scored March cohort, as served (with the actual outcome)
    workspace.churn.drift_psi          drift per feature and for the score (ADR-009)

The parity check itself is not a table: it is the P6 gate, recorded in MLflow and ADR-008.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:  # Databricks runs job scripts through exec(), without __file__
    for c in (globals().get("__file__"), sys.argv[0] if sys.argv else None, os.path.join(os.getcwd(), "_")):
        if c and (Path(c).resolve().parents[1] / "src" / "config.py").exists():
            return Path(c).resolve().parents[1]
    raise RuntimeError("repo root not found")


sys.path.insert(0, str(_repo_root()))
from src.config import load_config  # noqa: E402
from src.genai.dictionary import _LABELS  # noqa: E402
from src.spark_session import get_spark  # noqa: E402

COHORTS = (201702, 201703)


def comment(spark, table: str, text: str, columns: dict[str, str]) -> None:
    q = lambda t: t.replace("'", "\\'")  # noqa: E731
    spark.sql(f"COMMENT ON TABLE {table} IS '{q(text)}'")
    for col, desc in columns.items():
        spark.sql(f"ALTER TABLE {table} ALTER COLUMN `{col}` COMMENT '{q(desc)}'")


def main() -> None:
    cfg = load_config()
    P, D = cfg["paths"], cfg["databricks"]
    schema = D["model_name"].rsplit(".", 1)[0]
    spark = get_spark()
    published = []

    feats_dir = Path(P["features_dir"]) / "k14_w30"
    parts = [spark.read.parquet(str(feats_dir / f"cohort={c}")) for c in COHORTS if (feats_dir / f"cohort={c}").exists()]
    if parts:
        df = parts[0]
        for x in parts[1:]:
            df = df.unionByName(x)
        t = f"{schema}.features_k14_w30"
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(t)
        cols = {f: lab for f, (lab, _) in _LABELS.items() if f in df.columns}
        cols.update({"msno": "member id (dataset hash)", "cohort": "expiry month, yyyymm", "snapshot": "scoring day, yyyymmdd (expiry minus 14 days)",
                     "last_expire": "membership expiry, yyyymmdd", "label": "1 = did not renew within 30 days (official label)"})
        comment(spark, t, "Point-in-time features (k = 14 days before expiry, W = 30 days of history), built on Databricks by scripts/build_dataset.py.", cols)
        published.append(t)

    out = Path(P["outputs_dir"])
    if (out / "scores_201703.parquet").exists():
        t = f"{schema}.scores_march_2017"
        spark.read.parquet(str(out / "scores_201703.parquet")).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(t)
        comment(spark, t, "March 2017 members scored by the registered champion: calibrated probability, value and call order (ADR-004).", {
            "churn_probability": "calibrated chance of not renewing (isotonic + prior shift)", "member_value": "12 months of the current plan",
            "expected_value_at_risk": "churn_probability x member_value", "call_priority_rank": "1 = call first (expected value at risk)",
            "in_top_10pct": "on the default call list (top 10%)", "actual_churned": "what actually happened (for evaluation only)",
            "model_version": "Unity Catalog model and version that produced the score"})
        published.append(t)

    if (out / "drift_psi.parquet").exists():
        t = f"{schema}.drift_psi"
        spark.read.parquet(str(out / "drift_psi.parquet")).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(t)
        comment(spark, t, "Population Stability Index per model feature and for the score, training vs scored cohort (ADR-009).", {
            "psi": "population stability index", "band": "stable < 0.10 · watch 0.10-0.25 · alert > 0.25",
            "reference_mean": "mean in the training cohort", "current_mean": "mean in the scored cohort"})
        published.append(t)
    print("published:", published)


if __name__ == "__main__":
    main()
