# Explaining the model to sales and commercial readers

`python scripts/churn.py drivers` reads `global_drivers.json`, committed aggregates from `scripts/global_drivers.py` (no member rows). Numbers below are from that file; quote the command's output, not this page, if they differ.

## Method, in one line for the reader

"We measured how much the model relies on each signal across 200,000 members (TreeSHAP), and where its extra reach over today's rule comes from in the March 2017 backtest."

## Why the model reaches more leavers than today's rule (calling 10%, 86,215 members)

| | Today's rule | Model (ranked by churn chance) |
|---|---|---|
| Leavers reached | 54.1% | 65.5% |
| Who is on the list | Only manual renewers (104,817 of them; the list fills before reaching anyone else) | Mostly manual renewers; 13% of the list are auto-renew members |
| Auto-renew leavers reached (36% of all leavers) | 0% | 23% |

- **+8.2 points** come from auto-renew leavers the rule never calls.
- **+3.2 points** come from a better order among manual renewers (the remainder, so the parts add up to 65.5%).
- The served list ranks by churn chance × member value: 64.4% of leavers but 65.6% of the money at risk (P4 backtest); say which one you quote.

## What the model relies on (share of its attention)

| Theme | All members | Inside the 10% call list |
|---|---|---|
| Payment and plan (auto-renew, payment method, days since last payment, price, cancellations) | 68% | 82% |
| Listening (days listened, minutes, skips, days since last listened) | 19% | 13% |
| Membership history (tenure, sign-up) | 10% | 4% |
| Profile (city, age, gender) | 3% | 2% |

Top single signals: auto-renew (18%), payment method (18%), days since last payment (10%), plan list price (7%), days as a paying member (6%).

## Writing rules

1. Numbered points, business words; no "SHAP", "log-odds", "feature" or column names in the answer.
2. Lead with who the rule misses, then where the extra reach comes from, then what the model looks at, then money.
3. Shares are reliance, not direction: never say a signal "raises risk" from its share. Directions for one member come from `explain`.
4. Verified segment facts you may use: manual renewers churn at 38%, auto-renew members at 3% (March 2017).
