"""Global explainability for the business (skill iteration 2; shares only, since a feature's direction depends on its value): what the model looks at, and why it beats today's rule.

    SERVING_DIR=~/data/kkbox/serving python scripts/global_drivers.py
Writes data/outputs/p8_global_drivers.json: aggregates only (TreeSHAP shares by feature and by theme; the rule-gap
decomposition from p1_practitioner.json). No member id or member row is written (competition data terms, ADR-010).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from src.genai.dictionary import _LABELS
from src.services.store import ServingStore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "outputs" / "p8_global_drivers.json"
SAMPLE, SEED, SHARE = 200_000, 2026, 0.10
THEMES = {
    "Payment and plan": ["last_auto_renew", "last_is_cancel", "last_payment_method", "days_since_last_tx", "tx_count", "tx_count_window",
                         "tx_cancels", "tx_cancels_window", "tx_auto_renew_share", "tx_mean_discount", "tx_distinct_methods",
                         "last_plan_days", "last_list_price", "last_amount_paid"],
    "Listening": ["use_active_days", "use_active_days_recent", "days_since_last_play", "use_secs", "use_secs_per_day",
                  "use_secs_per_day_recent", "use_decline_ratio", "use_full_listen_share", "use_skip_share", "use_unique_songs_mean"],
    "Membership history": ["tenure_days", "registration_days", "registered_via"],
    "Profile (city, age, gender)": ["city", "age", "gender"],
}


def shares(contrib: np.ndarray, feats: list[str]) -> dict[str, float]:
    m = np.abs(contrib).mean(axis=0)
    return {f: float(v / m.sum()) for f, v in zip(feats, m)}


def rule_gap() -> dict:
    """Why the model reaches more leavers than today's rule at 10% calls, from the committed P1 results."""
    p = json.loads((ROOT / "data" / "outputs" / "p1_practitioner.json").read_text())
    leavers = p["test"]["leavers"]
    seg = {s["segment"]: s for s in p["segments_model_top10"]}
    man, auto = seg["Manual renewal"], seg["Auto-renew"]
    man_leavers, auto_leavers = man["members"] * man["churn_rate"], auto["members"] * auto["churn_rate"]
    rule_reach = next(r["reached"] for r in p["capture_curve"]["rule"] if abs(r["called"] - SHARE) < 1e-9)
    model_reach = next(r["reached"] for r in p["capture_curve"]["model"] if abs(r["called"] - SHARE) < 1e-9)
    calls = int(SHARE * p["test"]["members"])                              # as the API: floor
    assert calls < man["members"], "at 10% the rule's list holds only manual renewers"
    model_man, model_auto = man["leavers_reached"] * man_leavers, auto["leavers_reached"] * auto_leavers
    rule_man = rule_reach * leavers                                        # every leaver the rule reaches is a manual renewer
    return {"share_called": SHARE, "calls": calls, "leavers": leavers,
            "manual_renewers": man["members"], "manual_leavers": round(man_leavers), "auto_renew_leavers": round(auto_leavers),
            "auto_renew_share_of_leavers": auto_leavers / leavers,
            "rule_reach": rule_reach, "model_reach": model_reach,
            "rule_reaches_auto_renew_leavers": 0.0, "model_reaches_auto_renew_leavers": auto["leavers_reached"],
            "model_list_share_auto_renew": auto["share_of_call_list"],
            "points_from_auto_renew": model_auto / leavers,
            # remainder, so the parts add up to the published reach exactly (segment churn rates are stored rounded)
            "points_from_better_order_in_manual": model_reach - rule_reach - model_auto / leavers,
            "points_from_better_order_unrounded_check": (model_man - rule_man) / leavers}


def calibration() -> dict:
    """How well the forecast matched March 2017 (P4, isotonic + prior-shift EM): the basis of the skill's confidence levels."""
    c = json.loads((ROOT / "data" / "outputs" / "p4_rank_calibrate.json").read_text())["calibration"]
    used = c["isotonic_plus_em"]
    return {"expected_churn_rate": used["mean_predicted"], "actual_churn_rate": used["actual_rate"],
            "top_decile_expected": used["top_group_predicted"], "top_decile_actual": used["top_group_observed"],
            "ece": used["ece"], "forecast_reads": "low" if used["mean_predicted"] < used["actual_rate"] else "high"}


def main() -> None:
    store = ServingStore(os.environ.get("SERVING_DIR", str(Path.home() / "data" / "kkbox" / "serving")))
    feats, df = store.features, store.df
    rng = np.random.default_rng(SEED)
    sample = df.iloc[rng.choice(len(df), size=min(SAMPLE, len(df)), replace=False)]
    top = df.loc[store.order[: int(SHARE * len(df))]]
    c_all = store.booster.predict(sample[feats], pred_contrib=True)[:, :-1]
    c_top = store.booster.predict(top[feats], pred_contrib=True)[:, :-1]
    s_all, s_top = shares(c_all, feats), shares(c_top, feats)
    rows = sorted(({"feature": f, "label": _LABELS.get(f, (f,))[0], "share_all": s_all[f], "share_call_list": s_top[f]} for f in feats),
                  key=lambda r: -r["share_all"])
    themes = {t: {"share_all": sum(s_all.get(f, 0) for f in fs), "share_call_list": sum(s_top.get(f, 0) for f in fs)} for t, fs in THEMES.items()}
    covered = {f for fs in THEMES.values() for f in fs}
    assert covered >= set(feats), f"features without a theme: {set(feats) - covered}"
    out = {"method": "LightGBM TreeSHAP (pred_contrib); share = mean |contribution| of a feature / sum over features",
           "model_version": store.model_version, "cohort": "members expiring March 2017", "sample_members": len(sample), "seed": SEED,
           "call_list_share": SHARE, "call_list_members": len(top), "features": rows, "themes": themes, "rule_gap": rule_gap(), "calibration": calibration()}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({"top5": [(r["label"], round(r["share_all"], 3)) for r in rows[:5]], "themes": themes, "rule_gap": out["rule_gap"]}, indent=1))


if __name__ == "__main__":
    main()
