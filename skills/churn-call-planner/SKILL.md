---
name: churn-call-planner
description: Churn early warning and call planning for a music-subscription retention team, from a public model built on KKBox data (WSDM Cup 2018). Answers who to call, how many members to call for the best profit, what a call list is worth under a given save rate and cost per call, why a member is flagged and what to say, and whether ranking by value beats ranking by churn risk or today's rule. Use this skill whenever someone asks about subscription churn, renewal risk, retention call lists or campaigns, how many customers to contact, the value of a retention budget, or why a subscriber is at risk, even if they do not name the model. Do not use it for scoring real customers (only synthetic demo members are served), for telecom or other industries' live data, or for churn models in general.
---

# Churn Call Planner

Answers retention-planning questions from a public, read-only API: a calibrated LightGBM model that scores members 14 days before their plan expires, ranked by churn chance × member value. Results page: https://sabrinapribadi.github.io/subscription-churn-at-scale/

## How to call it

Run the bundled client; it needs only Python 3 and the internet, and it waits through the host's cold start:

```bash
python scripts/churn.py about                                    # data, period, definitions, check time (start here)
python scripts/churn.py call-list --share 0.1 --save-rate 0.2 --cost 20    # forecast: calling the top 10%
python scripts/churn.py what-if --save-rate 0.2 --cost 20        # backtest: best share and ranking methods
python scripts/churn.py score demo-007                           # one demo member's churn chance, value, priority
python scripts/churn.py explain demo-007                         # reasons and a suggested action
python scripts/churn.py chart profit --save-rate 0.2 --cost 20 --out profit.html   # profit by share called (line)
python scripts/churn.py chart reasons demo-007 --out reasons.html                  # what raises and lowers risk
python scripts/churn.py chart rankers --out rankers.html                           # ranking methods, backtest profit
```

The same tools exist over MCP at `https://subscription-churn-at-scale.vercel.app/mcp`.

## Workflow

1. **Run `about` first** so the answer opens with the data and its period.
2. **Pick the call from the question.** "How many to call" or a budget → `call-list` at the share their budget allows, plus `chart profit` for the best share. "Is value ranking worth it" → `what-if` and `chart rankers`, with today's rule from `references/data-sources.md`. A member → `explain` and `chart reasons`.
3. **Turn a budget into a share:** members called ÷ 862,158 (the March 2017 cohort). Say the share you used.
4. **Use the user's save rate and cost per call** when given; otherwise say you used the defaults (20%, NT$20) and that they are assumptions.
5. **Treat `not_found` as an answer.** Real members are not published (competition data terms); only demo-001 to demo-100 exist, and they are synthetic. Never estimate a real person's risk.

## Reading the numbers correctly

- **Forecast vs backtest.** `call-list` is a forecast: what calibrated churn chances expect among the members called. `what-if` is a backtest on members who actually churned in March 2017. They differ (e.g. top 10% at the defaults: NT$10.5M forecast vs NT$12.4M backtest); name which one you quote.
- `expected_profit` = save rate × value at risk among those called − members called × cost per call. A **save rate** of 20% means 1 in 5 called churners is kept; it is an assumption, not measured, because there was no live call test.
- `member_value` is 12 months of the member's current plan (amount paid per day × 365), in **NT$**.
- `churn_probability` is calibrated: 0.17 means about 17 in 100 members like this do not renew within 30 days of expiry.
- `priority_percentile` 89.5 means the member ranks above 89.5% of the cohort on churn chance × value.
- Reasons' `contribution` is a TreeSHAP log-odds contribution: how far that factor pushes the odds of not renewing, positive raises risk; compare sizes, do not read them as percentages.
- Data are from 2017; say so. The model shows how to plan, not today's customers.

## Answer structure

Retention managers decide in about five seconds whether an answer is useful, so keep it short, numbered and visual (`references/charts.md`):

1. **Data line** (one line): KKBox public data, members expiring March 2017 (862,158), scored 14 days ahead, model version, "checked <date> UTC".
2. **Headline** in bold: the answer in one sentence with its key number.
3. **2–4 numbered points**, one line each: the **baseline** for any comparison (today's rule: manual renewers first, then the longest idle; it reaches 54% of churners at 10% calls vs the model's 65%); the **assumptions** used (save rate, cost per call); the one **caveat** that would change the decision.
4. **One visual**: a line chart for "how many to call", diverging bars for "why this member", ranked bars for ranking methods. Give the file path and what it shows.
5. **To sharpen this** (one line): the team's real save rate from a small call test, cost per call, offer cost and capacity per agent.

## Limits

Historical public data (2017), one service in Taiwan; demo members are synthetic; save rate and costs are assumptions; no live A/B call test has been run.
