"""Client for the public subscription-churn API (standard library only).

    python churn.py about                                             # data, period, definitions and the time of this check
    python churn.py call-list [--share 0.1] [--save-rate 0.2] [--cost 20]   # expected economics of calling the top share (forecast)
    python churn.py what-if [--save-rate 0.2] [--cost 20]             # backtest on March 2017: best share and ranking methods
    python churn.py score MEMBER_ID                                   # one demo member: churn chance, value, priority
    python churn.py explain MEMBER_ID                                 # reasons behind the score and a suggested action
    python churn.py chart profit [--save-rate 0.2] [--cost 20] [--out chart.html]   # expected profit by share called (line)
    python churn.py chart reasons MEMBER_ID [--out chart.html]        # what raises and lowers a member's risk (diverging bars)
    python churn.py chart rankers [--save-rate 0.2] [--cost 20] [--out chart.html]  # backtest profit at 10% by ranking method

Real members are not served (competition data terms); demo members demo-001 to demo-100 are synthetic.
Amounts are New Taiwan dollars (NT$), the dataset's documented currency. Exit 0 on success, 1 on a network error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://subscription-churn-at-scale.vercel.app"
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


def data_line(ab: dict) -> str:
    return (f"Data: KKBox public competition data; members expiring March 2017 ({ab['test_cohort']['members']:,}), scored 14 days ahead, "
            f"trained on February 2017; model {ab['model_version']}; checked {ab['checked_at_utc']} UTC. Amounts in NT$.")


def make_chart(base: str, a: argparse.Namespace) -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import charts  # sibling module, imported only when a chart is asked for
    ab = about(base)
    if a.what == "profit":
        shares = [round(0.02 * i, 2) for i in range(1, 31)]          # 2-60%: wide enough that the best share is inside, not at the edge
        pts = [(s, get(base, "/call-list", {"share": s, "save_rate": a.save_rate, "cost_per_call": a.cost})["summary"]["expected_profit"]) for s in shares]
        best = max(pts, key=lambda p: p[1])
        page = charts.line_chart(pts, "Expected monthly profit by share of members called",
                                 f"Save rate {a.save_rate:.0%}, NT${a.cost:,.0f} per call. Best: call the top {best[0]:.0%} "
                                 f"(about {round(best[0] * ab['test_cohort']['members'], -2):,.0f} members) for about NT${best[1] / 1e6:.1f}M.",
                                 data_line(ab) + " Forecast from calibrated churn chances; profit = save rate × value at risk − calls × cost.",
                                 "Share of members called", "Expected profit (NT$)", y_fmt=lambda y: f"NT${y / 1e6:.1f}M",
                                 mark=best, mark_label=f"best: {best[0]:.0%}, NT${best[1] / 1e6:.1f}M")
    elif a.what == "reasons":
        e = get(base, f"/members/{urllib.parse.quote(a.member_id, safe="")}/explanation")
        if e.get("not_found"):
            raise SystemExit(e.get("detail", "member not found"))
        rows = [{"label": r["label"], "v": r["contribution"], "note": str(r["value"])} for r in e["reasons"]]
        s = e["score"]
        page = charts.diverging_bars(rows, f"Why {a.member_id} is flagged: {s['churn_probability']:.0%} chance of not renewing",
                                     f"Risk {s['risk_level']}; NT${s['member_value']:,.0f} a year at stake; suggested action: {e['suggested_action']}.",
                                     data_line(ab) + " Demo members are synthetic; reasons are the model's largest contributions.",
                                     "Raises risk", "Lowers risk")
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
    elif a.cmd == "what-if":
        out = get(a.base, "/what-if", {"save_rate": a.save_rate, "cost_per_call": a.cost})
    elif a.cmd == "score":
        out = get(a.base, f"/members/{urllib.parse.quote(a.member_id, safe="")}/score")
    else:
        out = get(a.base, f"/members/{urllib.parse.quote(a.member_id, safe="")}/explanation")
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
