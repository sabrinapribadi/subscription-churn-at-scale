# Table, chart or neither

The reader should get the answer in about five seconds from the headline. Add a visual only when it helps the decision, and only in units the reader already uses (members, NT$, % of leavers).

| The reader must... | Use | Command |
|---|---|---|
| Decide how many members to call, and how sure | **Confidence page**: dot plot of where each view stops, a pilot slider, the decision flow | `chart confidence --share X --save-rate S --cost C` |
| See only the profit curve | **Line chart** of expected profit by share called, best share marked | `chart profit --save-rate S --cost C` |
| See why the model beats today's rule | **Paired bars per 100 members who left**: rule (grey) vs model (blue), all leavers, manual renewers, auto-renew members | `chart drivers` |
| Compare ranking methods | **Ranked bars** of backtest profit at the same share | `chart rankers` |
| Understand why one member is flagged | **No chart**: a numbered list of reasons with strength words (strong, moderate, slight) | `explain MEMBER_ID` |
| Read exact values | **Table** (each chart has a table view) | — |

- Never: two y-axes, pies for rankings, a chart in a unit the reader does not use (log-odds), or a chart that repeats a table beside it.
- `chart reasons` exists for analysts who ask for it; do not add it to a business answer.

## Writing for five seconds

1. **Data line** (one line): data, cohort and period, check date.
2. **Headline** in bold: the answer in one sentence with the key number.
3. **2–4 numbered points**, each with one or two indented bullets for details: baseline, assumptions, how sure and the action (budgets), the caveat that changes the decision.
4. **One visual** with its file path, when it helps.
5. **To sharpen this** (one line).
