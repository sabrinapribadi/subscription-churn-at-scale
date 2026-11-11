"""What-if from value-by-budget curves (P4). Pure Python, so the public host needs no model libraries (ADR-010)."""

from __future__ import annotations

from src.services.contracts import WhatIf


def what_if_from(scenarios: dict, save_rate: float, cost_per_call: float) -> WhatIf:
    n, curves = scenarios["members"], scenarios["value_curves"]
    prof = {k: [(f, save_rate * v - cost_per_call * n * f) for f, v in c] for k, c in curves.items()}
    best = max(prof["expected_value"], key=lambda q: q[1])
    at10 = {k: round(next(p for f, p in c if abs(f - 0.10) < 1e-9), 0) for k, c in prof.items()}
    return WhatIf(save_rate=save_rate, cost_per_call=cost_per_call, best_share=best[0], best_members_called=int(n * best[0]),
                  best_monthly_profit=round(best[1], 0), profit_at_10pct=at10)
