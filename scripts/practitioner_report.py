"""Turn P1 test predictions into practitioner numbers and an appendix of ML metrics (rule R9).

Practitioner view: capture curve (share of leavers reached vs share of members called),
calibration bins, and segment cuts at the top-10% call list.
Appendix: PR-AUC, ROC-AUC, Gini, top-decile lift, H-measure, Brier, ECE, MPC and EMPC.

Writes data/outputs/p1_practitioner.json.

    python scripts/practitioner_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

import hmeasure
import numpy as np
import pandas as pd
import yaml
from empulse.metrics import empc_score, mpc_score
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

SCORES = {"rule": "score_rule", "realistic": "score_E2_realistic", "model": "score_E1_benchmark"}
FRACTIONS = [round(f, 2) for f in np.arange(0.01, 0.51, 0.01)]
# Verbraken et al. (2013) defaults: CLV 200, incentive 10, contact 1, accept rate ~ Beta(6, 14) (mean 0.30)
EMPC_PARAMS = dict(alpha=6, beta=14, clv=200, incentive_cost=10, contact_cost=1)
MPC_PARAMS = dict(accept_rate=0.3, clv=200, incentive_cost=10, contact_cost=1)


def capture_curve(y: np.ndarray, s: np.ndarray) -> dict:
    order = np.argsort(-s, kind="stable")
    cum = np.cumsum(y[order])
    n, P = len(y), y.sum()
    rows = []
    for f in FRACTIONS:
        k = int(n * f)
        rows.append({"called": f, "reached": round(float(cum[k - 1] / P), 4), "precision": round(float(cum[k - 1] / k), 4)})
    return rows


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[list, float]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        m = idx == b
        pred, obs = float(p[m].mean()), float(y[m].mean())
        ece += m.mean() * abs(pred - obs)
        rows.append({"bin": b + 1, "members": int(m.sum()), "predicted": round(pred, 4), "observed": round(obs, 4)})
    return rows, round(float(ece), 5)


def segments(df: pd.DataFrame, score: str, frac: float) -> list:
    thr = np.quantile(df[score], 1 - frac)
    df = df.assign(called=df[score] >= thr)
    cuts = {
        "Manual renewal": df["last_auto_renew"] == 0,
        "Auto-renew": df["last_auto_renew"] == 1,
        "New (< 6 months)": df["tenure_days"] < 180,
        "Established (≥ 6 months)": df["tenure_days"] >= 180,
    }
    out = []
    for name, m in cuts.items():
        seg = df[m]
        churners = seg["label"].sum()
        out.append({
            "segment": name, "members": int(len(seg)), "churn_rate": round(float(seg["label"].mean()), 4),
            "share_of_call_list": round(float(seg["called"].sum() / df["called"].sum()), 4),
            "leavers_reached": round(float(seg.loc[seg["called"], "label"].sum() / churners), 4) if churners else None,
            "precision_in_list": round(float(seg.loc[seg["called"], "label"].mean()), 4) if seg["called"].any() else None,
        })
    return out


def appendix(y: np.ndarray, s: np.ndarray, is_probability: bool) -> dict:
    roc = roc_auc_score(y, s)
    k = int(len(y) * 0.10)
    top = np.argsort(-s, kind="stable")[:k]
    out = {
        "pr_auc": average_precision_score(y, s), "roc_auc": roc, "gini": 2 * roc - 1,
        "top_decile_lift": y[top].mean() / y.mean(), "h_measure": hmeasure.h_score(y, rankdata(s) / len(s)),  # rank-invariant; library needs [0, 1]
        "mpc": mpc_score(y, s, **MPC_PARAMS), "mpc_optimal_share": mpc_score.optimal_rate(y, s, **MPC_PARAMS),
        "empc": empc_score(y, s, **EMPC_PARAMS), "empc_optimal_share": empc_score.optimal_rate(y, s, **EMPC_PARAMS),
    }
    if is_probability:
        out["brier"] = brier_score_loss(y, s)
        out["ece"] = calibration(y, s)[1]
    return {m: round(float(v), 4) for m, v in out.items()}


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    store = Path(cfg["paths"]["parquet_dir"]).expanduser().parent
    df = pd.read_parquet(store / "predictions" / "p1_test_201703.parquet")
    y = df["label"].to_numpy()
    frac = cfg["validation"]["top_k_fraction"]

    report = {
        "test": {"cohort": 201703, "members": int(len(df)), "leavers": int(y.sum()), "churn_rate": round(float(y.mean()), 4)},
        "capture_curve": {name: capture_curve(y, df[col].to_numpy()) for name, col in SCORES.items()},
        "calibration_model": calibration(y, df[SCORES["model"]].to_numpy())[0],
        "segments_model_top10": segments(df, SCORES["model"], frac),
        "appendix": {name: appendix(y, df[col].to_numpy(), name != "rule") for name, col in SCORES.items()},
        "assumptions": {"empc": EMPC_PARAMS, "mpc": MPC_PARAMS, "source": "Verbraken, Verbeke & Baesens (2013), IEEE TKDE 25(5)"},
    }
    out = Path(cfg["paths"]["outputs_dir"]) / "p1_practitioner.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("test", "appendix", "segments_model_top10")}, indent=1))
    print("calibration:", [(r["predicted"], r["observed"]) for r in report["calibration_model"]])
    print("capture @5/10/20%:", {n: [c["reached"] for c in cc if c["called"] in (0.05, 0.1, 0.2)] for n, cc in report["capture_curve"].items()})


if __name__ == "__main__":
    main()
