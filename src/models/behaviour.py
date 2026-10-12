"""P3 behaviour arms (ADR-003): sequence arrays, shape statistics, masked autoencoder, Mantis embeddings."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

CHANNELS = ["num_25", "num_50", "num_75", "num_985", "num_100", "num_unq", "minutes"]
MIN, SKIP, FULL, UNQ = 6, 0, 4, 5  # channel indices


# ---------------------------------------------------------------------------- arrays
def load_sequences(seq_dir, msno: pd.Series, days: int, only_these: bool = False) -> np.ndarray:
    """Long-format rows (msno, pos, channels) → float16 array [members, days, channels], zeros for inactive days.

    float16 keeps one cohort at ~0.7 GB (log1p values < 12, so precision loss is negligible).
    """
    dset = ds.dataset(seq_dir, format="parquet", partitioning=None)
    if only_these:  # just these members' rows; single-threaded batches avoid an Arrow/OpenMP deadlock on macOS
        keep = set(msno.tolist())
        parts = []
        for b in dset.to_batches(columns=["msno", "pos", *CHANNELS], use_threads=False, batch_size=1_000_000):
            df = b.to_pandas()
            parts.append(df[df["msno"].isin(keep)])
        t = pd.concat(parts, ignore_index=True)
    else:
        t = dset.to_table().to_pandas()
    index = pd.Series(np.arange(len(msno)), index=msno.to_numpy())
    rows = index.reindex(t["msno"].to_numpy()).to_numpy()
    keep = ~np.isnan(rows)
    X = np.zeros((len(msno), days, len(CHANNELS)), dtype=np.float16)
    X[rows[keep].astype(np.int64), t["pos"].to_numpy()[keep].astype(np.int64)] = t[CHANNELS].to_numpy(np.float16)[keep]
    del t
    return X


# ---------------------------------------------------------------------------- arm A
def _slope(y: np.ndarray) -> np.ndarray:
    t = np.arange(y.shape[1], dtype=np.float32)
    t = (t - t.mean()) / (t.std() + 1e-9)
    return (y * t).mean(axis=1)


def _longest_zero_run(active: np.ndarray) -> np.ndarray:
    run = np.zeros(active.shape[0], dtype=np.int32)
    best = np.zeros_like(run)
    for d in range(active.shape[1]):
        run = np.where(active[:, d], 0, run + 1)
        best = np.maximum(best, run)
    return best


def shape_features(X: np.ndarray, snapshot: pd.Series) -> pd.DataFrame:
    """Arm A: hand-crafted shape statistics of the 60-day sequence (all computed before the snapshot)."""
    X = X.astype(np.float32, copy=False) if X.dtype != np.float32 and X.nbytes < 2e9 else X
    m = X[:, :, MIN].astype(np.float32)
    active = m > 0
    counts = np.expm1(X[:, :, :5].astype(np.float32))
    plays = counts.sum(axis=2) + 1e-9
    skip = counts[:, :, SKIP] / plays
    full = counts[:, :, FULL] / plays
    last7, prior23 = m[:, -7:].mean(axis=1), m[:, -30:-7].mean(axis=1)
    last14, prior46 = slice(-14, None), slice(None, -14)
    # weekend share: day-of-week of each position, from each member's snapshot date
    snap_dow = snapshot.astype(str).map(lambda s: date(int(s[:4]), int(s[4:6]), int(s[6:])).weekday()).to_numpy()
    offs = np.arange(X.shape[1]) - X.shape[1]
    dow = (snap_dow[:, None] + offs[None, :]) % 7
    weekend = (dow >= 5)
    tot = np.expm1(m).sum(axis=1) + 1e-9
    return pd.DataFrame({
        "seq_minutes_slope_60": _slope(m),
        "seq_minutes_slope_30": _slope(m[:, -30:]),
        "seq_last7_vs_prior23": (last7 + 1e-3) / (prior23 + 1e-3),
        "seq_active_last7": active[:, -7:].sum(axis=1),
        "seq_active_last30": active[:, -30:].sum(axis=1),
        "seq_active_slope_60": _slope(active.astype(np.float32)),
        "seq_longest_gap": _longest_zero_run(active),
        "seq_volatility": m.std(axis=1) / (m.mean(axis=1) + 1e-3),
        "seq_weekend_share": (np.expm1(m) * weekend).sum(axis=1) / tot,
        "seq_skip_trend": np.nanmean(np.where(active[:, last14], skip[:, last14], np.nan), axis=1)
                          - np.nanmean(np.where(active[:, prior46], skip[:, prior46], np.nan), axis=1),
        "seq_full_trend": np.nanmean(np.where(active[:, last14], full[:, last14], np.nan), axis=1)
                          - np.nanmean(np.where(active[:, prior46], full[:, prior46], np.nan), axis=1),
        "seq_unique_slope_60": _slope(X[:, :, UNQ].astype(np.float32)),
    })


# ---------------------------------------------------------------------------- arm B
def train_masked_autoencoder(X: np.ndarray, dim: int = 16, epochs: int = 3, mask_rate: float = 0.3,
                             batch: int = 2048, device: str = "cpu", seed: int = 7):
    """Arm B: 1-D CNN encoder trained to reconstruct masked days (labels never used). Returns (model, mean, std)."""
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    sample = X[np.random.default_rng(seed).choice(len(X), min(len(X), 100_000), replace=False)].astype(np.float32)
    mu = sample.reshape(-1, X.shape[2]).mean(axis=0)
    sd = sample.reshape(-1, X.shape[2]).std(axis=0) + 1e-6
    del sample
    C = X.shape[2]

    class MAE(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = nn.Sequential(
                nn.Conv1d(C + 1, 64, 5, padding=2), nn.GELU(),
                nn.Conv1d(64, 64, 5, padding=4, dilation=2), nn.GELU(),
                nn.Conv1d(64, 64, 5, padding=8, dilation=4), nn.GELU(),
            )
            self.to_z = nn.Linear(64 * 2, dim)
            self.dec = nn.Sequential(nn.Conv1d(64 + dim, 64, 5, padding=2), nn.GELU(), nn.Conv1d(64, C, 1))

        def embed(self, x, mask):
            h = self.enc(torch.cat([x * (1 - mask), mask], dim=1))
            return h, self.to_z(torch.cat([h.mean(dim=2), h.amax(dim=2)], dim=1))

        def forward(self, x, mask):
            h, z = self.embed(x, mask)
            zz = z[:, :, None].expand(-1, -1, x.shape[2])
            return self.dec(torch.cat([h, zz], dim=1)), z

    model = MAE().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    rng = np.random.default_rng(seed)
    norm = lambda xb: ((xb.astype(np.float32) - mu) / sd).transpose(0, 2, 1)  # [B, C, T]
    for ep in range(epochs):
        order = rng.permutation(len(X))
        total = 0.0
        for i in range(0, len(order), batch):
            xb = torch.from_numpy(np.ascontiguousarray(norm(X[np.sort(order[i:i + batch])]))).to(device)
            mask = (torch.rand(xb.shape[0], 1, xb.shape[2], device=device) < mask_rate).float()
            rec, _ = model(xb, mask)
            loss = (((rec - xb) ** 2) * mask).sum() / (mask.sum() * C + 1e-9)
            opt.zero_grad(); loss.backward(); opt.step()
            total += loss.item() * xb.shape[0]
        print(f"  MAE epoch {ep + 1}/{epochs}: masked-reconstruction MSE {total / len(X):.4f}", flush=True)
    return model, mu, sd


def encode_masked_autoencoder(model, mu, sd, X: np.ndarray, batch: int = 8192, device: str = "cpu") -> np.ndarray:
    import torch

    out = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(X), batch):
            xb = torch.from_numpy(np.ascontiguousarray(((X[i:i + batch].astype(np.float32) - mu) / sd).transpose(0, 2, 1))).to(device)
            _, z = model.embed(xb, torch.zeros(xb.shape[0], 1, xb.shape[2], device=device))
            out.append(z.cpu().numpy())
    return np.concatenate(out)


# ---------------------------------------------------------------------------- arm C
def mantis_embeddings(X: np.ndarray, channels: list[int], device: str = "cpu", batch: int = 512) -> np.ndarray:
    """Arm C: frozen Mantis-8M, one channel at a time, sequences interpolated to 512 steps."""
    import torch
    from mantis.architecture import Mantis8M
    from mantis.trainer import MantisTrainer

    net = Mantis8M(device=device).from_pretrained("paris-noah/Mantis-8M")
    trainer = MantisTrainer(device=device, network=net)
    parts = []
    for c in channels:
        x = torch.from_numpy(X[:, None, :, c].astype(np.float32))
        x512 = torch.nn.functional.interpolate(x, size=512, mode="linear", align_corners=False).numpy()
        parts.append(trainer.transform(x512, batch_size=batch))
        del x, x512
        if device == "mps":
            torch.mps.empty_cache()
    return np.concatenate(parts, axis=1)
