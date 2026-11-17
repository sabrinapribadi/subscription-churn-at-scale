# Table, chart or neither

The reader should get the answer in about five seconds from the headline and one visual.

| The reader must... | Use | Command |
|---|---|---|
| Decide how many members to call | **Line chart** of expected profit by share called, best share marked | `chart profit --save-rate S --cost C` |
| Understand why one member is flagged | **Diverging bars**: reasons that raise risk (red, right) and lower it (blue, left), largest first | `chart reasons MEMBER_ID` |
| Compare ranking methods | **Ranked bars** of backtest profit at the same share | `chart rankers` |
| Read one member's numbers | **No chart**: headline and 2–4 numbered points | `score MEMBER_ID` |
| Read exact values | **Table** (each chart has a table view) | — |

Never: two y-axes, pies for rankings, or a chart that repeats a table beside it.

## Writing for five seconds

1. **Data line** (one line): data, cohort and period, check date.
2. **Headline** in bold: the answer in one sentence with the key number.
3. **2–4 numbered points**: baseline, assumptions, the caveat that changes the decision.
4. **One visual** with its file path.
5. **To sharpen this** (one line).
