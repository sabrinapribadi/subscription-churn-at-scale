"""Phase 3: does the shape of daily listening add signal? (ADR-003)

Base = P2 model (k = 14, W = 30 tabular features), train Feb-2017 → test Mar-2017 (official).
Arms added on top: A shape statistics · B masked autoencoder · C Mantis-8M (frozen, on a sample).
Reports PR-AUC, churners reached at 10%, and reach among auto-renew churners; builds personas.

    python scripts/behaviour_ablation.py --stage embed     # arms A + B, every member
    python scripts/behaviour_ablation.py --stage mantis    # arm C, 100k sample per cohort
    python scripts/behaviour_ablation.py --stage score     # models, gate, personas
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.behaviour import (encode_masked_autoencoder, load_sequences, mantis_embeddings,  # noqa: E402
                                  shape_features, train_masked_autoencoder)

# LightGBM / scikit-learn are imported only in the score stage: on macOS their OpenMP runtime
# conflicts with PyTorch's and segfaults Mantis inference when both are loaded (ADR-003 Am. 2).

TRAIN, TEST, K, DAYS, GATE = 201702, 201703, 14, 60, 0.02


def device() -> str:
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def score(train: pd.DataFrame, test: pd.DataFrame, cols: list[str], frac: float) -> tuple[dict, np.ndarray]:
    from src.evaluation.metrics import evaluate
    from src.models.baseline import fit
    model = fit(train, cols)
    p = model.predict_proba(test[cols])[:, 1]
    y = test["label"].to_numpy()
    res = evaluate(y, p, frac)
    top = p >= np.quantile(p, 1 - frac)
    auto = (test["last_auto_renew"].fillna(0).to_numpy() == 1) & (y == 1)
    res["auto_renew_churners_reached"] = float(top[auto].mean())
    res["best_iteration"] = int(model.best_iteration_)
    return res, p


def load_base(cfg, store, W):
    from src.features.build import select_window
    from src.models.baseline import NON_FEATURES, prepare
    raw = ds.dataset(store / "features" / f"k{K}_wmulti", format="parquet", partitioning=None).to_table().to_pandas()
    mapping = select_window(list(raw.columns), W)
    data = prepare(raw[list(mapping)].rename(columns=mapping)); del raw; gc.collect()
    base_cols = [c for c in data.columns if c not in NON_FEATURES]
    train = data[data["cohort"] == TRAIN].reset_index(drop=True)
    test = data[data["cohort"] == TEST].reset_index(drop=True)
    return train, test, base_cols


def stage_embed(cfg, store, work):
    """Arms A and B for every member → work/arms_{cohort}.parquet (msno + arm columns)."""
    dev = device()
    seq_root = store / "sequences" / f"k{K}_d{DAYS}"
    keys = {c: pd.read_parquet(store / "features" / f"k{K}_wmulti" / f"cohort={c}", columns=["msno", "snapshot"]) for c in (TRAIN, TEST)}
    Xtr = load_sequences(seq_root / f"cohort={TRAIN}", keys[TRAIN]["msno"], DAYS)
    t0 = time.time()
    mae, mu, sd = train_masked_autoencoder(Xtr, dim=16, epochs=3, device=dev)
    print(f"arm B trained in {time.time() - t0:.0f}s", flush=True)
    for c in (TRAIN, TEST):
        X = Xtr if c == TRAIN else load_sequences(seq_root / f"cohort={c}", keys[c]["msno"], DAYS)
        A = shape_features(X, keys[c]["snapshot"])
        B = encode_masked_autoencoder(mae, mu, sd, X, device=dev)
        out = A.assign(msno=keys[c]["msno"].to_numpy())
        for j in range(B.shape[1]):
            out[f"mae_{j}"] = B[:, j]
        out.to_parquet(work / f"arms_{c}.parquet", index=False)
        print(f"arms A+B for {c}: {len(out):,} members", flush=True)
        del X, A, B, out; gc.collect()


def stage_mantis(cfg, store, work, n):
    """Arm C on a fixed random sample per cohort → work/mantis_{cohort}.parquet.

    Samples are loaded before PyTorch is imported (Arrow and PyTorch thread pools can deadlock on macOS).
    """
    seq_root = store / "sequences" / f"k{K}_d{DAYS}"
    samples = {}
    for c in (TRAIN, TEST):
        msno = pd.read_parquet(store / "features" / f"k{K}_wmulti" / f"cohort={c}", columns=["msno"])["msno"]
        idx = np.sort(np.random.default_rng(7 + c % 100).choice(len(msno), n, replace=False))
        sample = msno.iloc[idx].reset_index(drop=True)
        t0 = time.time()
        samples[c] = (sample, load_sequences(seq_root / f"cohort={c}", sample, DAYS, only_these=True))
        print(f"loaded {n:,} sequences for {c} in {time.time() - t0:.0f}s", flush=True)
    dev = device()
    for c in (TRAIN, TEST):
        sample, X = samples.pop(c)
        t0 = time.time()
        Z = mantis_embeddings(X, channels=[6, 4, 0, 5], device=dev, batch=256)
        out = pd.DataFrame(Z, columns=[f"mraw_{j}" for j in range(Z.shape[1])]).assign(msno=sample.to_numpy())
        out.to_parquet(work / f"mantis_{c}.parquet", index=False)
        print(f"arm C for {c}: {n:,} members in {time.time() - t0:.0f}s", flush=True)
        del X, Z, out; gc.collect()


def stage_score(cfg, store, work, frac, W):
    import mlflow
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler
    train, test, base_cols = load_base(cfg, store, W)
    arm_tr, arm_te = pd.read_parquet(work / f"arms_{TRAIN}.parquet"), pd.read_parquet(work / f"arms_{TEST}.parquet")
    train, test = train.merge(arm_tr, on="msno", how="left"), test.merge(arm_te, on="msno", how="left")
    A_cols = [c for c in arm_tr.columns if c.startswith("seq_")]
    B_cols = [c for c in arm_tr.columns if c.startswith("mae_")]
    mlflow.set_tracking_uri("sqlite:///mlflow.db"); mlflow.set_experiment("p3_behaviour")
    results = {"setup": {"train": TRAIN, "test": TEST, "lead_days": K, "window_days": W, "sequence_days": DAYS, "gate": GATE},
               "full_test": {}, "sample_test": {}}
    configs = {"base": [], "A_shape": A_cols, "B_autoencoder": B_cols, "A_plus_B": A_cols + B_cols}
    preds = {}
    for name, extra in configs.items():
        t0 = time.time()
        res, p = score(train, test, base_cols + extra, frac)
        preds[name] = p; results["full_test"][name] = res
        with mlflow.start_run(run_name=name):
            mlflow.log_metrics({m: v for m, v in res.items() if isinstance(v, float)})
        print(f"{name:14} PR-AUC {res['pr_auc']:.4f}  reach@10% {res['recall_at_k']:.3f}  auto-renew reach {res['auto_renew_churners_reached']:.3f}  {time.time() - t0:.0f}s", flush=True)
    if (work / f"mantis_{TRAIN}.parquet").exists():
        m_tr, m_te = pd.read_parquet(work / f"mantis_{TRAIN}.parquet"), pd.read_parquet(work / f"mantis_{TEST}.parquet")
        raw_cols = [c for c in m_tr.columns if c.startswith("mraw_")]
        pca = PCA(n_components=16, random_state=7).fit(m_tr[raw_cols])
        tr_s, te_s = train.merge(m_tr, on="msno"), test.merge(m_te, on="msno")
        for df in (tr_s, te_s):
            Z = pca.transform(df[raw_cols])
            for j in range(16):
                df[f"mantis_{j}"] = Z[:, j]
        C_cols = [f"mantis_{j}" for j in range(16)]
        results["setup"]["mantis_sample"] = int(len(te_s))
        for name, extra in {"base": [], "A_shape": A_cols, "B_autoencoder": B_cols, "C_mantis": C_cols}.items():
            res, _ = score(tr_s, te_s, base_cols + extra, frac)
            results["sample_test"][name] = res
            print(f"[sample] {name:14} PR-AUC {res['pr_auc']:.4f}  reach@10% {res['recall_at_k']:.3f}  auto-renew reach {res['auto_renew_churners_reached']:.3f}", flush=True)

    base = results["full_test"]["base"]["pr_auc"]
    best = max((k for k in results["full_test"] if k != "base"), key=lambda k: results["full_test"][k]["pr_auc"])
    results["gate"] = {"best_arm": best, "delta_pr_auc": results["full_test"][best]["pr_auc"] - base,
                       "passed": bool(results["full_test"][best]["pr_auc"] - base >= GATE)}
    if results["sample_test"]:
        sb = results["sample_test"]["base"]["pr_auc"]
        results["gate"]["sample_deltas"] = {k: v["pr_auc"] - sb for k, v in results["sample_test"].items() if k != "base"}

    # personas: k-means on standardized shape statistics (test cohort)
    Zs = StandardScaler().fit(train[A_cols].fillna(0)).transform(test[A_cols].fillna(0))
    km = KMeans(n_clusters=5, n_init=4, random_state=7).fit(Zs[np.random.default_rng(7).choice(len(Zs), 200_000, replace=False)])
    lab = km.predict(Zs)
    p_best = preds[best]; top = p_best >= np.quantile(p_best, 1 - frac); churn = (test["label"] == 1).to_numpy()
    results["personas"] = []
    for c in range(5):
        m = lab == c; g = test.loc[m]
        results["personas"].append({
            "cluster": c, "members": int(m.sum()), "share": float(m.mean()), "churn_rate": float(g["label"].mean()),
            "auto_renew_share": float((g["last_auto_renew"] == 1).mean()),
            "reached_in_top10": float(top[m & churn].mean()) if (m & churn).any() else None,
            "median_minutes_per_day": float(g["use_secs_per_day"].median() / 60),
            "median_tenure_days": float(g["tenure_days"].median()),
            "median_registration_days": float(g["registration_days"].median()),
            "manual_renewal_share": float((g["last_auto_renew"] == 0).mean()),
            "median_plan_days": float(g["last_plan_days"].median()),
            "profile": {k: float(g[k].median()) for k in ["seq_minutes_slope_60", "seq_last7_vs_prior23", "seq_active_last30", "seq_longest_gap", "seq_weekend_share", "seq_skip_trend"]},
        })
    out = Path(cfg["paths"]["outputs_dir"]) / "p3_behaviour.json"
    out.write_text(json.dumps(results, indent=2, default=float))
    print(json.dumps(results["gate"], indent=1)); print("wrote", out)


def main() -> None:
    cfg = yaml.safe_load(Path("configs/default_config.yaml").read_text())
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["embed", "mantis", "score"], required=True)
    ap.add_argument("--mantis-sample", type=int, default=100_000)
    a = ap.parse_args()
    frac, W = cfg["validation"]["top_k_fraction"], cfg["framing"]["window_days_selected"]
    store = Path(cfg["paths"]["parquet_dir"]).expanduser().parent
    work = store / "p3"; work.mkdir(exist_ok=True)
    {"embed": lambda: stage_embed(cfg, store, work),
     "mantis": lambda: stage_mantis(cfg, store, work, a.mantis_sample),
     "score": lambda: stage_score(cfg, store, work, frac, W)}[a.stage]()


if __name__ == "__main__":
    main()
