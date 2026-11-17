---
name: churn-call-planner
description: Churn early warning and call planning for a music-subscription retention team, from a public model built on KKBox data (WSDM Cup 2018). Answers who to call, how many members to call for the best profit, what a call list is worth under a given save rate and cost per call, how confident those numbers are and what to do about it, why a member is flagged and what to say, and why the model beats today's rule in plain business terms. Use this skill whenever someone asks about subscription churn, renewal risk, retention call lists or campaigns, how many customers to contact, the value of a retention budget, or why a subscriber is at risk, even if they do not name the model. Do not use it for scoring real customers (only synthetic demo members are served), for telecom or other industries' live data, or for churn models in general.
---

# Churn Call Planner

Answers retention-planning questions from a public, read-only API: a calibrated LightGBM model that scores members 14 days before their plan expires, ranked by churn chance × member value. Results page: https://sabrinapribadi.github.io/subscription-churn-at-scale/

## How to call it

Run the bundled client; it needs only Python 3 and the internet, and it waits through the host's cold start:

```bash
python scripts/churn.py about                                    # data, period, definitions, check time (start here)
python scripts/churn.py call-list --share 0.1 --save-rate 0.2 --cost 20    # forecast: calling the top 10%
python scripts/churn.py confidence --share 0.1 --save-rate 0.2 --cost 20   # how sure: level, floor to commit to, pilot size
python scripts/churn.py what-if --save-rate 0.2 --cost 20        # backtest: best share and ranking methods
python scripts/churn.py drivers                                  # what the model looks at; why it beats today's rule
python scripts/churn.py score demo-007                           # one demo member's churn chance, value, priority
python scripts/churn.py explain demo-007                         # reasons (with strength words) and a suggested action
python scripts/churn.py chart confidence --share 0.1 --save-rate 0.2 --cost 20 --out confidence.html   # where each view stops; pilot slider; decision
python scripts/churn.py chart profit --save-rate 0.2 --cost 20 --out profit.html   # profit by share called (line)
python scripts/churn.py chart drivers --out drivers.html                           # where the extra reach over today's rule comes from
python scripts/churn.py chart rankers --out rankers.html                           # ranking methods, backtest profit
```

The same tools exist over MCP at `https://subscription-churn-at-scale.vercel.app/mcp`.

## Workflow

1. **Run `about` first** so the answer opens with the data and its period.
2. **Pick the call from the question.**
   - "How many to call", a budget or capacity → `call-list` at that share, **`confidence`** at the same share, and **`chart confidence`** (where each view stops, a pilot simulation, the decision after the pilot).
   - "Why is the model better than what we do" or "is value ranking worth it" → **`drivers`** and `chart drivers`, plus `what-if` for the money.
   - One member → `explain`; **no chart** (see below).
3. **Turn a budget into a share:** members called ÷ 862,158 (the March 2017 cohort). Say the share you used.
4. **Use the user's save rate and cost per call** when given; otherwise say you used the defaults (20%, NT$20) and that they are assumptions.
5. **Treat `not_found` as an answer.** Real members are not published (competition data terms); only demo-001 to demo-100 exist, and they are synthetic. Never estimate a real person's risk.

## How sure is a number, and what to do about it

Every budget answer says how sure it is **in numbers, not a label**, then turns that into a number to commit to and an action (`references/confidence.md`). Use `confidence` and `chart confidence`:

- **How sure, in numbers:** how many of the three views (forecast, half the save rate, March 2017 backtest) say calling more pays (e.g. "3 of 3"), where each says to stop (e.g. 18%, 26%, 34%) and the spread in points; the profit at half the save rate and the break-even save rate.
- **Why the forecast is a floor:** in March 2017 the forecast expected 6.1% of members to churn and 7.3% did (top 10%: 39.6% expected, 47.2% actual), so forecast profits read low.
- **Commit to the floor** (the smallest best share, in members) when all views agree on the direction; give the range above it.
- **Pilot:** `pilot.calls` measures the save rate within ±5 points (95%); say its cost and the decision it settles (the four outcomes on the chart).
- The `level` field (high, medium, low) is for routing only; do not print it.

## Explaining the model to a business audience

When asked why the model beats today's rule, or what it looks at, use `drivers` and write for sales and commercial readers: numbered points, their words, no "SHAP", "log-odds" or feature names (`references/explainability.md`).

1. **Who the rule misses:** at 10% calls the rule's list is only manual renewers; auto-renew members are about 36% of leavers and the rule never calls them.
2. **Where the extra reach comes from:** about 8 points from auto-renew leavers, about 3 points from a better order among manual renewers (54% → 65% of leavers, model ranked by churn chance; the served value ranking reaches 64% of leavers and 66% of the money at risk).
3. **What the model looks at:** payment and plan signals about two-thirds of its attention (about four-fifths inside the call list), listening about a fifth, membership history about a tenth, profile (city, age, gender) about 3%.
4. **What it is worth:** the backtest profit of each ranking from `what-if`, and the caveat.

Shares say how much the model relies on a signal, not whether a value raises or lowers risk; do not claim a direction for a signal from them.

## Reading the numbers correctly

- **Forecast vs backtest.** `call-list` is a forecast: what calibrated churn chances expect among the members called. `what-if` is a backtest on members who actually churned in March 2017. Name which one you quote.
- `expected_profit` = save rate × value at risk among those called − members called × cost per call. A **save rate** of 20% means 1 in 5 called churners is kept; it is an assumption, not measured, because there was no live call test.
- `member_value` is 12 months of the member's current plan (amount paid per day × 365), in **NT$**.
- `churn_probability` is calibrated: 0.17 means about 17 in 100 members like this do not renew within 30 days of expiry.
- `priority_percentile` 89.5 means the member ranks above 89.5% of the cohort on churn chance × value.
- **Reasons:** say each one's `strength` (strong, moderate, slight) and whether it raises or lowers risk; never quote the contribution number.
- Data are from 2017; say so. The model shows how to plan, not today's customers.

## Answer structure

Retention managers decide in about five seconds whether an answer is useful, so keep it short and numbered (`references/charts.md`):

1. **Data line** (one line): KKBox public data, members expiring March 2017 (862,158), scored 14 days ahead, model version, "checked <date> UTC".
2. **Headline** in bold: the answer in one sentence with its key number.
3. **2–4 numbered points**, one line each: the **baseline** for any comparison (today's rule: manual renewers first, then the longest idle; 54% of churners at 10% calls vs the model's 65%); the **assumptions**; for budgets, **how sure in numbers and the action**.
4. **One visual only when it helps the decision**: the confidence page for "how many to call" (`chart profit` when only the curve is asked for), stacked bars for "why the model beats the rule", ranked bars for ranking methods. For one member, no chart: five reasons read faster as a list.
5. **To sharpen this** (one line): the team's real save rate from the pilot, offer cost and capacity per agent.

## Limits

Historical public data (2017), one service in Taiwan; demo members are synthetic; save rate and costs are assumptions; no live A/B call test has been run.
