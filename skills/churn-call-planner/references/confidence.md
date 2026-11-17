# Confidence levels and what to do with them

A budget answer is only useful if the reader knows how far to trust it. `python scripts/churn.py confidence --share S --save-rate R --cost C` returns everything below.

## Three views of the best share

| View | What it is | Why it matters |
|---|---|---|
| Forecast | Calibrated churn chances at the user's save rate (`call-list` sweep, 2–60%) | The planning number |
| Half the save rate | The same forecast with the save rate halved | Stress test: the save rate is the least known input |
| Backtest | Members who actually churned in March 2017 (`what-if`) | What really happened with this ranking |

## Levels (routing only; say the numbers, not the label)

| Level | Rule | Say | Do |
|---|---|---|---|
| High | Profit positive at half the save rate; all three views agree on the direction; forecast and backtest bests within 5 points | The number, plainly | Act on it |
| Medium | Positive at half the save rate; direction agrees; bests differ by more than 5 points | "Calling more pays; how much more is uncertain" with the range | Commit to the floor (smallest best share); run the pilot before scaling to the range |
| Low | Not positive at half the save rate, or the views disagree on the direction | No target | Break-even save rate and the pilot only |

## Evidence behind the forecast (March 2017, committed results)

- The calibrated forecast expected **6.1%** of members to churn; **7.3%** did. In the top 10% it expected **39.6%** and **47.2%** churned.
- So forecast profits **read low**: treat them as a floor, and the backtest as the check on what happened.
- Calibration error (ECE) **0.012**, just above the 0.010 bar set before training (reported as a failed gate).

## Turning uncertainty into an action

1. **Floor:** the smallest of the three best shares; calling up to it pays in every view. Give it in members.
2. **Range:** smallest to largest best share, in members; the size of the decision still open.
3. **Break-even save rate:** cost per call × members called ÷ value at risk among them; below it the campaign loses money.
4. **Pilot:** calls needed to measure the save rate within ±5 points at 95%: churners needed = 1.96² × r(1 − r) ÷ 0.05², divided by the share of called members expected to churn (forecast, so the pilot is a little larger than needed). Example at r = 25% and 5.8% called: 289 churners, about 600 calls.
5. **Decision after the pilot:** the four outcomes in the chart's flow (below), set by the measured save rate against the assumption, half of it and break-even.

## The chart (`chart confidence`)

1. **Where each view says to stop:** one row per view, a dot at its best share with the profit there; the user's capacity as a dashed line; the uncertain range shaded. A dot plot, not bars: the question is *where*, not *how much*.
2. **Pilot simulation:** a slider from 100 to 1,000 calls; churners reached, the save-rate margin (±), the save-rate range, the profit range at the floor and the pilot's cost update as it moves.
3. **Decision after the pilot:** a flow with four outcomes by measured save rate: at or above the assumption, scale toward the forecast–backtest range; between half and the assumption, call up to the floor; between break-even and half, keep current capacity; below break-even, stop.
