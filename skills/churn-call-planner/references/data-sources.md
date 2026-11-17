# Data, definitions and baselines

## Data

| What | Detail | Source |
|---|---|---|
| Members and plans | KKBox music subscriptions: 6.8M members, 410M listening records, transactions | WSDM Cup 2018 public competition data (Kaggle); amounts in New Taiwan dollars, per the dataset's field descriptions |
| Test cohort | Members whose plan expires in March 2017: 862,158, of whom 62,616 (7.3%) churned | `data/outputs/p1_practitioner.json` |
| Training | February 2017 expiries (out-of-time: train on February, score March) | ADR-002 |
| Churner | No renewal within 30 days of expiry (the competition's definition) | ADR-001 |
| Lead time | Scored 14 days before expiry, using only data available then (point-in-time features) | ADR-001, ADR-002 |
| Member value | Amount paid per day on the last plan × 365 (list price per day when paid = 0) | ADR-004 |
| Value at risk in the cohort | NT$107.9M among actual churners | `data/outputs/p4_rank_calibrate.json` |
| Privacy | Real member rows are never served; the API holds cohort aggregates and 100 synthetic demo members | ADR-010 |

## Baselines

| Method | What it does | Churners reached when calling 10% | Backtest profit at 10% (save 20%, NT$20 per call) |
|---|---|---|---|
| **Today's rule** | Manual renewers first (auto-renew off), then the members idle longest since they last listened | 54.1% | not computed |
| Churn chance only | Calibrated LightGBM probability | 65.2% | NT$12.41M |
| **Churn chance × member value (used)** | Same model, ranked by expected value at risk | 64.4% (65.6% of value at risk) | **NT$12.43M** |
| Learned ranker (LambdaMART) | Trained directly to rank by value | 48.9% | NT$9.70M (failed its gate) |

- **Why value ranking is used:** it reaches slightly fewer churners but more of the money at risk; the industry practice of selecting customers by value, not risk alone (Venkatesan & Kumar 2004; Gupta et al. 2006), cited in ADR-011.
- **Plain-language test result:** calling the top 10% by the model reaches about 65 in 100 churners; today's rule reaches about 54.

## Assumptions (not data)

- **Save rate:** share of called churners who stay; central 20%, sensitivity 10–30%. No live call test exists, so this is the largest uncertainty.
- **Cost per call:** NT$20 central, sensitivity 0–50.
- Ask the team for their measured save rate and cost to replace these.
