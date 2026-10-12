# ADR-003: Behavioural Signal — Hand-Crafted Shape vs Self-Supervised Encoder vs Foundation-Model Embeddings

**Status:** Accepted — gate failed for all arms; embeddings kept for personas only
**Date:** 2026-10-12
**Deciders:** Sabrina Pribadi

---

## Context and Problem Statement

P1 and P2 showed that payment and renewal state carries most of the signal; listening aggregates add ~6% of model gain and 30 days of history is as good as 180. Yet a third of churners (≈22,000 a month) are **auto-renew members who cancel**, and the P1 list reaches only 1 in 4 of them. Their payment state looks safe until they cancel, so any early warning must come from **how their listening changes**, not how much they listen.

The question: **"Does the shape of daily listening add signal that aggregates miss — enough to matter on the call list?"**

## Decision Drivers

- Must be tested against the P2 model with the *same* features, split and lead time (k = 14, W = 30, train Feb → test Mar)
- Must beat a cheap, explainable alternative, not just the baseline — otherwise the simpler option wins
- Embeddings must be learned only from data before each member's snapshot (no label leakage; ADR-001)
- Must run on a laptop (Apple MPS / CPU) for ~1.7M member sequences

## Considered Options

| Arm | Method | Evidence | Why considered |
|-----|--------|----------|----------------|
| **A. Shape statistics** | Hand-crafted sequence features: trend slopes, last-7 vs prior-23 ratio, longest inactive streak, weekday/weekend mix, volatility, skip-share trend | Rolling-window behavioural drivers (arXiv 2606.06776, 2026) | Cheap, explainable; the bar the learned arms must clear |
| **B. Self-supervised masked autoencoder** | Small 1-D CNN encoder trained to reconstruct masked days of the 60-day × 7-channel sequence; bottleneck = embedding | Masked modelling for time series: Ti-MAE (arXiv 2301.08871), TimeMAE (2026); SimMTM | Learns this domain's patterns without labels |
| **C. Frozen foundation-model embeddings** | Mantis-8M (pre-trained on synthetic series, contrastive), used as a frozen encoder per channel | Mantis (arXiv 2502.15637, 2025); MOMENT used the same way | No training on our data; tests whether generic time-series knowledge transfers |
| D. End-to-end supervised sequence model | LSTM / Transformer trained on churn labels | RNN vs Transformer on time-varying RFM (Annals of OR 2023) | **Deferred** — answers a different question (replace GBM), not "add signal to GBM" |

## Decision Outcome

Run arms **A, B, C** as ablations on top of the P2 model (k = 14, W = 30 tabular features):

- **Input sequence:** 60 days before the snapshot × 7 channels — log1p of plays by completion bucket (5), unique songs, minutes; inactive days = 0.
- **Arm B training data:** sequences of Feb-2017 training members only (labels unused); applied unchanged to March.
- **Arm C:** Mantis-8M frozen; sequences interpolated to its input length; per-channel embeddings reduced with PCA fitted on training members.
- **Personas (practitioner output):** k-means on the winning arm's embeddings → named behaviour types with churn rates.

**Pre-registered gate (from ADR-002):** PR-AUC(GBM + best arm) ≥ PR-AUC(GBM) + 0.02 on Mar-2017.
**Secondary (reported, not gating):** share of auto-renew churners reached in the top 10%.

**Falsification conditions:**

| Result | Diagnosis | Next action |
|--------|-----------|-------------|
| No arm reaches +0.02 | Listening shape is weak at 14 days' lead | Report negative result; keep personas for practitioners; P4 proceeds on the P2 model |
| A ≥ B and A ≥ C | Simple shape features capture what the encoders learn | Keep A (cheap, explainable); drop encoders |
| B or C clears the gate, but not on auto-renew churners | Gains come from members the list already reaches | Report; P4 decides whether the extra cost is worth it |
| B or C clears the gate *and* lifts auto-renew reach | Behaviour shape finds the hidden churners | Adopt the arm; add to the serving path (P5) |

## Amendment 1 (2026-10-12, before any arm was run) — Arm C on a sample

Measured Mantis-8M throughput on this machine (Apple M2, MPS, no other load): **767 single-channel sequences/s**. Embedding every member of both cohorts on 4 channels (minutes, full listens, skips, unique songs) would take ~2.5 hours.

**Decision:** arm C runs on a random **100,000-member sample per cohort**. To keep the comparison fair, **base, A, B and C are all re-trained and re-scored on the same samples** ("sample test"). The gate for A and B stays on the full March cohort; arm C's gate is judged on the sample (same +0.02 threshold).

## Amendment 2 (2026-10-12) — Arm C crash fixed, design unchanged

The first two arm-C runs crashed (segfault). Cause: on macOS, LightGBM and PyTorch load different OpenMP runtimes; with both in one process, Mantis inference segfaults. Fix: LightGBM and scikit-learn are imported only in the scoring stage, so embedding runs in a process without them. No change to sample size, channels, or gate.

## Results (2026-10-12)

| Arm | PR-AUC, full Mar-2017 (862,158) | Δ vs base | PR-AUC, 100k sample | Δ vs sample base | Auto-renew churners reached |
|-----|------|------|------|------|------|
| Base (P2 model, W = 30) | 0.5614 | — | 0.5495 | — | 22.8% |
| A · shape statistics | 0.5652 | **+0.0038** | 0.5508 | +0.0013 | 22.5% |
| B · masked autoencoder | 0.5633 | +0.0019 | 0.5498 | +0.0002 | 22.9% |
| A + B | 0.5646 | +0.0032 | — | — | 22.7% |
| C · Mantis-8M (frozen) | — | — | 0.5527 | +0.0031 | 23.7% |

**Gate verdict:** not cleared by any arm (best +0.0038 vs +0.02 required; within the 0.003 run-to-run noise measured in P2). **Falsification row 1 applies:** listening shape is weak at 14 days' lead. Embeddings are not added to the serving model; P4 proceeds on the P2 model.

**Personas (k-means on arm A statistics, Mar-2017):** steady regulars 37.6% (churn 7.7%), fading 28.2% (7.1%), silent payers 20.3% (4.0%; list reaches 36% of their churners), re-engaging 13.6% (11.4%; median tenure 410 days, 25% manual renewal), just came back 0.4% (3.5%). Used for practitioner messaging, not scoring.

## Positive Consequences

- A clean three-way comparison: cheap vs learned vs pre-trained, all on the same split
- Personas are useful to practitioners even if the gate fails

## Negative Consequences

- Sequence extraction adds a Spark job and ~1.5 GB of arrays per cohort (stored outside the repo)
- Mantis inference on ~860k test members is the slowest step; batch on MPS

## Related Decisions

- ADR-001 Amendment 3 (W = 30 for tabular features; encoder chooses its own window)
- ADR-002 (gate and out-of-time split)

## References

- Ti-MAE: Self-Supervised Masked Time Series Autoencoders — arXiv 2301.08871
- TimeMAE: Self-Supervised Representations of Time Series with Decoupled Masked Autoencoders — arXiv 2303.00320 (ACM, 2026)
- Mantis: Lightweight Foundation Model for Time Series Classification — arXiv 2502.15637
- A Rolling-Window Framework for Churn Prediction and Behavioral Driver Identification — arXiv 2606.06776
- Exploiting time-varying RFM measures for customer churn prediction with deep neural networks — Annals of Operations Research (2023)
