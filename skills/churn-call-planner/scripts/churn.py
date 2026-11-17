"""Client for the public subscription-churn API (standard library only).

    python churn.py about                                             # data, period, definitions and the time of this check
    python churn.py call-list [--share 0.1] [--save-rate 0.2] [--cost 20]   # expected economics of calling the top share (forecast)
    python churn.py what-if [--save-rate 0.2] [--cost 20]             # backtest on March 2017: best share and ranking methods
    python churn.py score MEMBER_ID                                   # one demo member: churn chance, value, priority
    python churn.py explain MEMBER_ID                                 # reasons behind the score and a suggested action
    python churn.py chart profit [--save-rate 0.2] [--cost 20] [--out chart.html]   # expected profit by share called (line)
    python churn.py chart reasons MEMBER_ID [--out chart.html]        # what raises and lowers a member's risk (diverging bars)
    python churn.py chart rankers [--save-rate 0.2] [--cost 20] [--out chart.html]  # backtest profit at 10% by ranking method
    python churn.py confidence --share 0.058 [--save-rate 0.2] [--cost 20]  # how sure: forecast, backtest, half save rate; floor and pilot
    python churn.py drivers                                           # what the model looks at, and why it beats today's rule
    python churn.py chart drivers [--out chart.html]                  # where the model's extra reach over today's rule comes from
    python churn.py chart confidence --share 0.058 [...] [--out chart.html]   # where each view stops; pilot simulation; decision flow

Real members are not served (competition data terms); demo members demo-001 to demo-100 are synthetic.
Amounts are New Taiwan dollars (NT$), the dataset's documented currency. Exit 0 on success, 1 on a network error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://subscription-churn-at-scale.vercel.app"
DRIVERS = Path(__file__).resolve().parents[1] / "references" / "global_drivers.json"   # committed aggregates (scripts/global_drivers.py)
SHARES = [round(0.02 * i, 2) for i in range(1, 31)]                  # 2-60%: wide enough that the best share is inside, not at the edge
RANKERS = {"expected_value": "Churn chance × member value (used)", "probability": "Churn chance only", "lambdamart": "Learned ranker (LambdaMART)"}


def get(base: str, path: str, params: dict | None = None, timeout: float = 60) -> dict:
    url = base.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "churn-call-planner-skill/1.0", "Accept": "application/json"})
    last = None
    for attempt in range(2):                      # one retry covers a cold start or a transient error
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:                     # unknown member: a valid answer, returned as data
                return {"not_found": True, **json.loads(e.read().decode(errors="replace") or "{}")}
            if e.code < 500:
                raise SystemExit(f"HTTP {e.code} for {url}: {e.read().decode(errors='replace')[:300]}")
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(3 * (attempt + 1))
    print(f"error: could not reach {url}: {last}", file=sys.stderr)
    sys.exit(1)


def quote_id(member_id: str) -> str:
    """Escape every reserved character, '/' included, so an id can never change the API path."""
    return urllib.parse.quote(member_id, safe="")


def about(base: str) -> dict:
    root = get(base, "/")
    return {"checked_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),  # noqa: UP017 - Python 3.8+
            "data": "KKBox music subscriptions (WSDM Cup 2018, public competition data): 410M listening records, 6.8M members",
            "test_cohort": {"who": "members whose plan expires in March 2017", "members": root.get("cohort_members"),
                            "scored": "14 days before expiry", "trained_on": "February 2017 expiries (out-of-time test)"},
            "churner": "no renewal within 30 days of expiry", "currency": "New Taiwan dollars (NT$)",
            "member_value": "amount paid per day on the last plan × 365 (12 months of revenue if retained)",
            "assumptions": "save rate (share of called churners kept) and cost per call are inputs, not data; defaults 20% and NT$20",
            "model_version": root.get("model_version"), "data_terms": root.get("data_terms"), "results_page": root.get("results_page")}


def sweep(base: str, save: float, cost: float) -> list[tuple[float, float]]:
    """Forecast expected profit at each share in SHARES."""
    return [(s, get(base, "/call-list", {"share": s, "save_rate": save, "cost_per_call": cost})["summary"]["expected_profit"]) for s in SHARES]


def confidence(base: str, share: float, save: float, cost: float) -> dict:
    """How sure the numbers are, as a level with its evidence, a number to commit to, and the action that raises confidence.

    Three views of the best share: forecast at the user's save rate, forecast at half of it (stress test), backtest on March 2017.
    high   = profit positive even at half the save rate, all three agree on the direction, and forecast and backtest bests within 5 points;
    medium = positive at half the save rate and the direction agrees, but the bests differ by more than 5 points: commit to the floor;
    low    = not positive at half the save rate, or the views disagree on the direction: commit to nothing beyond a pilot.
    """
    cal = json.loads(DRIVERS.read_text())["calibration"]
    n = about(base)["test_cohort"]["members"]
    here = get(base, "/call-list", {"share": share, "save_rate": save, "cost_per_call": cost})["summary"]
    half = get(base, "/call-list", {"share": share, "save_rate": save / 2, "cost_per_call": cost})["summary"]
    f_best = max(sweep(base, save, cost), key=lambda p: p[1])
    p_best = max(sweep(base, save / 2, cost), key=lambda p: p[1])
    wi = get(base, "/what-if", {"save_rate": save, "cost_per_call": cost})
    bests = {"forecast": f_best[0], "half_save_rate": p_best[0], "backtest": wi["best_share"]}
    lo, hi = min(bests.values()), max(bests.values())
    direction = "call more" if share < lo else ("call fewer" if share > hi else "mixed")
    safe = half["expected_profit"] > 0
    agree = abs(bests["forecast"] - bests["backtest"]) <= 0.05
    level = "high" if safe and direction != "mixed" and agree else ("medium" if safe and direction != "mixed" else "low")
    precision = here["expected_churners"] / here["members_called"]
    churners = math.ceil(1.96 ** 2 * save * (1 - save) / 0.05 ** 2)            # measure the save rate to within ±5 points (95%)
    pilot = math.ceil(churners / precision / 100) * 100
    floor = get(base, "/call-list", {"share": lo, "save_rate": save, "cost_per_call": cost})["summary"]
    views_more = sum(b > share for b in bests.values())
    return {"level": level, "direction": direction, "share": share, "members_called": here["members_called"],
            "profit_forecast": here["expected_profit"], "profit_at_half_save_rate": half["expected_profit"],
            "best_share": bests, "best_profit": {"forecast": f_best[1], "half_save_rate": p_best[1], "backtest": wi["best_monthly_profit"]},
            "views_say_call_more": views_more, "views": len(bests), "spread_points": round(100 * (hi - lo)),
            "floor": {"share": lo, "members_called": floor["members_called"], "profit_forecast": floor["expected_profit"],
                      "expected_churners": floor["expected_churners"], "expected_value_at_risk": floor["expected_value_at_risk"],
                      "break_even_save_rate": cost * floor["members_called"] / floor["expected_value_at_risk"]},
            "range_share": [lo, hi], "range_members": [int(n * lo), int(n * hi)], "best_members": {k: int(n * v) for k, v in bests.items()},
            "break_even_save_rate": cost * here["members_called"] / here["expected_value_at_risk"],
            "pilot": {"calls": pilot, "churners_needed": churners, "precision_forecast": precision, "margin": 0.05},
            "calibration": {"expected_churn_rate": cal["expected_churn_rate"], "actual_churn_rate": cal["actual_churn_rate"],
                            "top_decile_expected": cal["top_decile_expected"], "top_decile_actual": cal["top_decile_actual"],
                            "meaning": "in March 2017 the forecast expected fewer churners than happened, so forecast profits read low (a floor)"},
            "save_rate": save, "cost_per_call": cost}


def drivers() -> dict:
    """What the model looks at (TreeSHAP shares by theme and feature) and why it beats today's rule (committed aggregates)."""
    d = json.loads(DRIVERS.read_text())
    return {"method": d["method"], "model_version": d["model_version"], "sample_members": d["sample_members"],
            "themes": sorted(({"theme": k, **v} for k, v in d["themes"].items()), key=lambda r: -r["share_all"]),
            "top_features": [{"label": r["label"], "share_all": r["share_all"], "share_call_list": r["share_call_list"]} for r in d["features"][:6]],
            "rule_gap": d["rule_gap"]}


def strength(c: float) -> str:
    """Plain words for a reason's size (TreeSHAP log-odds): readers compare words, not log-odds."""
    a = abs(c)
    return "strong" if a >= 1.0 else ("moderate" if a >= 0.3 else "slight")


def data_line(ab: dict) -> str:
    return (f"Data: KKBox public competition data; members expiring March 2017 ({ab['test_cohort']['members']:,}), scored 14 days ahead, "
            f"trained on February 2017; model {ab['model_version']}; checked {ab['checked_at_utc']} UTC. Amounts in NT$.")


def make_chart(base: str, a: argparse.Namespace) -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import charts  # sibling module, imported only when a chart is asked for
    ab = about(base)
    if a.what == "profit":
        pts = sweep(base, a.save_rate, a.cost)
        best = max(pts, key=lambda p: p[1])
        page = charts.line_chart(pts, "Expected monthly profit by share of members called",
                                 f"Save rate {a.save_rate:.0%}, NT${a.cost:,.0f} per call. Best: call the top {best[0]:.0%} "
                                 f"(about {round(best[0] * ab['test_cohort']['members'], -2):,.0f} members) for about NT${best[1] / 1e6:.1f}M.",
                                 data_line(ab) + " Forecast from calibrated churn chances; profit = save rate × value at risk − calls × cost.",
                                 "Share of members called", "Expected profit (NT$)", y_fmt=lambda y: f"NT${y / 1e6:.1f}M",
                                 mark=best, mark_label=f"best: {best[0]:.0%}, NT${best[1] / 1e6:.1f}M")
    elif a.what == "reasons":
        e = get(base, f"/members/{quote_id(a.member_id)}/explanation")
        if e.get("not_found"):
            raise SystemExit(e.get("detail", "member not found"))
        rows = [{"label": r["label"], "v": r["contribution"], "note": str(r["value"])} for r in e["reasons"]]
        s = e["score"]
        page = charts.diverging_bars(rows, f"Why {a.member_id} is flagged: {s['churn_probability']:.0%} chance of not renewing",
                                     f"Risk {s['risk_level']}; NT${s['member_value']:,.0f} a year at stake; suggested action: {e['suggested_action']}.",
                                     data_line(ab) + " Demo members are synthetic; reasons are the model's largest contributions.",
                                     "Raises risk", "Lowers risk")
    elif a.what == "confidence":
        page = charts.confidence_page(confidence(base, a.share, a.save_rate, a.cost), data_line(ab))
    elif a.what == "drivers":
        g = drivers()["rule_gap"]
        rule, auto, order = 100 * g["rule_reach"], 100 * g["points_from_auto_renew"], 100 * g["points_from_better_order_in_manual"]
        rows = [{"label": "Today's rule", "parts": [rule, 0, 0]}, {"label": "Model (churn chance)", "parts": [rule, order, auto]}]
        page = charts.stacked_bars(rows, f"Calling {g['share_called']:.0%}: the model reaches {100 * g['model_reach']:.1f}% of leavers, today's rule {rule:.1f}%",
                                   f"{auto:.1f} points come from auto-renew members, {100 * g['auto_renew_share_of_leavers']:.0f}% of all leavers, whom the rule "
                                   f"never calls; {order:.1f} points from a better order among manual renewers.",
                                   data_line(ab) + " Backtest on members who actually churned (P1, model ranked by churn chance); aggregates only.",
                                   [("Manual renewers, as many as the rule reaches", "--ctx"), ("More manual renewers (better order)", "--c1"),
                                    ("Auto-renew leavers (rule never calls them)", "--c2")], unit=lambda v: f"{v:.1f}%")
    else:
        w = get(base, "/what-if", {"save_rate": a.save_rate, "cost_per_call": a.cost})
        rows = [{"label": RANKERS.get(k, k), "v": v, "cat": "Used" if k == "expected_value" else "Alternative",
                 "text": f"NT${v / 1e6:.1f}M", "tip": f"Backtest profit when calling the top 10%: NT${v:,.0f}"} for k, v in w["profit_at_10pct"].items()]
        page = charts.ranked_bars(rows, "Backtest profit when calling the top 10%, by ranking method",
                                  f"March 2017 members who actually churned; save rate {a.save_rate:.0%}, NT${a.cost:,.0f} per call.",
                                  data_line(ab), ["Used", "Alternative"])
    out = Path(a.out).resolve()
    out.write_text(page, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=DEFAULT_BASE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("about")
    for name in ("call-list", "what-if"):
        p = sub.add_parser(name)
        if name == "call-list":
            p.add_argument("--share", type=float, default=0.10, help="share of members to call, 0-1 (default 0.10)")
        p.add_argument("--save-rate", type=float, default=0.20); p.add_argument("--cost", type=float, default=20.0)
    for name in ("score", "explain"):
        sub.add_parser(name).add_argument("member_id")
    ch = sub.add_parser("chart"); csub = ch.add_subparsers(dest="what", required=True)
    for name in ("profit", "rankers"):
        p = csub.add_parser(name); p.add_argument("--save-rate", type=float, default=0.20); p.add_argument("--cost", type=float, default=20.0)
        p.add_argument("--out", default="chart.html")
    r = csub.add_parser("reasons"); r.add_argument("member_id"); r.add_argument("--out", default="chart.html")
    csub.add_parser("drivers").add_argument("--out", default="chart.html")
    cc = csub.add_parser("confidence"); cc.add_argument("--share", type=float, required=True); cc.add_argument("--out", default="chart.html")
    cc.add_argument("--save-rate", type=float, default=0.20); cc.add_argument("--cost", type=float, default=20.0)
    cf = sub.add_parser("confidence"); cf.add_argument("--share", type=float, required=True)
    cf.add_argument("--save-rate", type=float, default=0.20); cf.add_argument("--cost", type=float, default=20.0)
    sub.add_parser("drivers")
    a = ap.parse_args(argv)

    if a.cmd == "chart":
        print(f"chart written: {make_chart(a.base, a)}")
        return
    if a.cmd == "about":
        out = about(a.base)
    elif a.cmd == "call-list":
        if not 0 < a.share <= 1:
            raise SystemExit("share must be between 0 and 1, e.g. 0.1 for the top 10%")
        out = get(a.base, "/call-list", {"share": a.share, "save_rate": a.save_rate, "cost_per_call": a.cost})
    elif a.cmd == "confidence":
        if not 0 < a.share <= 1:
            raise SystemExit("share must be between 0 and 1, e.g. 0.058 for 50,000 of 862,158 members")
        out = confidence(a.base, a.share, a.save_rate, a.cost)
    elif a.cmd == "drivers":
        out = drivers()
    elif a.cmd == "what-if":
        out = get(a.base, "/what-if", {"save_rate": a.save_rate, "cost_per_call": a.cost})
    elif a.cmd == "score":
        out = get(a.base, f"/members/{quote_id(a.member_id)}/score")
    else:
        out = get(a.base, f"/members/{quote_id(a.member_id)}/explanation")
        for r in out.get("reasons", []):
            r["strength"] = strength(r["contribution"])
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
