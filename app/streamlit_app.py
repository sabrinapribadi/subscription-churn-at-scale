"""Streamlit companion app (R26): plan a call campaign with your own capacity, explore the demo members, call the live API.

Only what the static results page cannot do; every number comes from the committed public snapshot or the public API.
Run: streamlit run app/streamlit_app.py   (theme in .streamlit/config.toml at the repository root)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan as P  # sibling module; the app runs from the repo root on Streamlit Cloud

API = os.environ.get("CHURN_API_BASE", P.API)
st.set_page_config(page_title="Churn call planner", layout="wide", initial_sidebar_state="expanded")

dark = getattr(getattr(st.context, "theme", None), "type", "light") == "dark"
C = {"line": "#4d94e8" if dark else "#2a78d6", "you": "#d95926" if dark else "#eb6834", "muted": "#8a93a3" if dark else "#6b7385",
     "raise": "#e66767" if dark else "#e34948", "lower": "#4d94e8" if dark else "#2a78d6",
     "risk": ["#f08a5d", "#c4562a", "#7a3a22"] if dark else ["#b8441a", "#eb6834", "#f6b896"]}   # high, medium, low: one orange ramp

st.html("""<style>
.hero-eyebrow{font-size:.78rem;letter-spacing:.09em;text-transform:uppercase;font-weight:600;opacity:.65;margin:0}
.hero-title{font-family:'Space Grotesk',Inter,system-ui,sans-serif;font-size:clamp(2rem,4.2vw,3rem);font-weight:700;line-height:1.05;margin:.2rem 0 .4rem}
.hero-sub{font-size:1.02rem;opacity:.8;max-width:70ch;margin:0 0 .4rem}
.brief-w{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:#7fb2f0;margin-bottom:.2rem}
.brief-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin:.2rem 0 .3rem}
.bcard{border:1px solid #2a3240;border-radius:10px;padding:8px 12px;font-size:.86rem;line-height:1.4;background:#11161e}
.bcard a{color:#7fb2f0}
.note{border-left:3px solid #4d94e8;padding:.6rem .9rem;border-radius:0 .5rem .5rem 0;background:rgba(77,148,232,.10);line-height:1.5}
</style>""")


@st.cache_data
def snapshot() -> dict:
    return P.load()


snap = snapshot()
grid = snap["call_grid"]


def ntd(v: float) -> str:
    sign, v = ("−" if v < 0 else ""), abs(v)
    return f"{sign}NT${v / 1e6:.1f}M" if v >= 1e6 else f"{sign}NT${v:,.0f}"


# Sidebar: the campaign, kept across tabs
with st.sidebar:
    st.subheader("Your campaign")
    agents = st.number_input("Call agents", 1, 2000, 50, key="agents")
    per_day = st.number_input("Calls per agent per day", 1, 300, 80, key="per_day")
    days = st.number_input("Working days before renewal", 1, 14, 10, key="days",
                           help="Members are scored 14 days before their plan expires, so about 10 working days.")
    st.divider()
    save = st.slider("Save rate: share of called churners kept", 0.05, 0.50, 0.20, 0.01, format="%.2f", key="save",
                     help="An assumption, not data. A small call test measures it.")
    cost = st.slider("Cost per call (NT$)", 0, 100, 20, 1, key="cost")
    offer = st.slider("Retention offer per saved member (NT$)", 0, 500, 0, 10, key="offer",
                      help="Not in the API: the app subtracts offer × expected saved members.")
    st.divider()
    st.caption(f"Model `{snap['model_version']}` · snapshot {snap['built']}")
    st.caption("Free Streamlit Community Cloud app: it sleeps after 12 hours without visits; the first visit wakes it (up to a minute).")

calls = int(agents * per_day * days)
p = P.plan(grid, calls, save, cost, offer)
rows = P.curve(grid, save, cost, offer)
top = P.best(rows)
bt = P.backtest_best(snap["scenarios"], save, cost)

# 1. Hero, KPI strip and the brief (R22, R26): the first screen is what LinkedIn's preview captures
hl = P.headline(snap)
st.html(f"""<p class="hero-eyebrow">KKBox public data · members expiring March 2017 · {grid['members']:,} members · amounts in NT$</p>
<h1 class="hero-title">Churn call planner</h1>
<p class="hero-sub">Who to call two weeks before renewal, and what a call campaign is worth with your team's capacity and costs.</p>""")
kp = st.columns(4)
kp[0].metric("Leavers reached, calling 10%", f"{hl['model_reach']:.0%}", f"today's rule: {hl['rule_reach']:.0%}", delta_color="off", delta_arrow="off", border=True)
kp[1].metric("Backtest profit a month", ntd(hl["profit_10pct"]), "March 2017, calling 10%", delta_color="off", delta_arrow="off", border=True)
kp[2].metric("Leavers the rule never calls", f"{hl['auto_per_100']:.0f} per 100", "auto-renew; the model reaches", delta_color="off", delta_arrow="off", border=True)
kp[3].metric("Members scored", f"{hl['members']:,}", "14 days before expiry", delta_color="off", delta_arrow="off", border=True)
items = P.brief()
st.html('<div class="brief-grid">' + "".join(f'<div class="bcard"><div class="brief-w">{w}</div><div>{P.md_html(lines[0])}</div></div>' for w, lines in items) + "</div>")
with st.expander("Full brief"):
    for w, lines in items:
        st.markdown(f"**{w}:** " + " ".join(lines))
st.caption(f"[Results page]({P.PAGES}) · [Technical walkthrough]({P.PAGES}build.html) · [Demo API]({P.API}/docs) · [Source]({P.REPO}) · "
           f"Free Streamlit app: it sleeps after 12 hours without visits; the [results page]({P.PAGES}) is always on and carries every result.")

plan_tab, members_tab, agent_tab, api_tab = st.tabs(["Plan a campaign", "Explore demo members", "Ask the agent", "Ask the live API"])

# 2. Plan with your own capacity and costs
with plan_tab:
    st.subheader(f"Calling the top {p['share']:.1%} (about {p['members_called']:,} members) reaches about {p['expected_churners']:,.0f} "
                 f"likely churners; expected profit {ntd(p['expected_profit'])} a month")
    st.caption(f"Your capacity: {agents:,} agents × {per_day:,} calls × {days} days = {calls:,} calls, rounded to the nearest 0.1% of members "
               "(the snapshot's grid, as in the API). Change it in the sidebar.")
    m = st.columns(4)
    m[0].metric("Members called", f"{p['members_called']:,}", f"top {p['share']:.1%} of {grid['members']:,}",
                delta_color="off", delta_arrow="off", border=True)
    m[1].metric("Likely churners", f"{p['expected_churners']:,.0f}", f"{p['expected_saved']:,.0f} kept",
                delta_color="off", delta_arrow="off", border=True)
    m[2].metric("Value at risk", ntd(p["expected_value_at_risk"]), "12 months of revenue", delta_color="off", delta_arrow="off", border=True)
    m[3].metric("Expected profit", ntd(p["expected_profit"]), "a month, net", delta_color="off", delta_arrow="off", border=True)

    if p["expected_profit"] <= 0:
        st.warning("At these costs the campaign loses money: call fewer members, cut the offer, or test whether the save rate is higher.")
    elif calls < top["members_called"]:
        st.success(f"**Capacity is the limit:** profit keeps rising to the top {top['share']:.1%} (about {top['members_called']:,} calls, "
                   f"{ntd(top['expected_profit'])}). More agents or days would pay.")
    else:
        st.info(f"**You have more capacity than pays:** the best is the top {top['share']:.1%} (about {top['members_called']:,} calls, "
                f"{ntd(top['expected_profit'])}); calls beyond it cost more than they keep.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("**Expected profit by share of members called**")
        df = pd.DataFrame(rows).assign(label=lambda d: d["share"].map(lambda s: f"{s:.1%}"))
        base = alt.Chart(df).encode(x=alt.X("share:Q", title="Share of members called", axis=alt.Axis(format="%", grid=False)))
        area = base.mark_area(line={"color": C["line"], "strokeWidth": 2}, color=alt.Gradient(
            gradient="linear", x1=1, x2=1, y1=1, y2=0,
            stops=[alt.GradientStop(color="rgba(42,120,214,0.02)", offset=0), alt.GradientStop(color="rgba(42,120,214,0.28)", offset=1)])
        ).encode(y=alt.Y("expected_profit:Q", title="Expected profit (NT$)", axis=alt.Axis(format="~s")))
        hover = base.mark_point(size=90, opacity=0).encode(
            y="expected_profit:Q", tooltip=[alt.Tooltip("label:N", title="Share"), alt.Tooltip("members_called:Q", title="Members called", format=","),
                                            alt.Tooltip("expected_profit:Q", title="Expected profit (NT$)", format=",.0f")])
        you = alt.Chart(pd.DataFrame([{"share": p["share"], "y": df["expected_profit"].max() * 0.06, "t": "your capacity"}]))
        peak = alt.Chart(pd.DataFrame([{**top, "t": f"best: {top['share']:.1%}"}]))
        layers = (area + hover
                  + you.mark_rule(color=C["you"], strokeWidth=2, strokeDash=[5, 4]).encode(x="share:Q")
                  + you.mark_text(align="left", dx=6, dy=-4, color=C["you"], fontWeight=600).encode(x="share:Q", y="y:Q", text="t:N")
                  + peak.mark_point(size=110, filled=True, color=C["line"], stroke="white", strokeWidth=2).encode(x="share:Q", y="expected_profit:Q")
                  + peak.mark_text(dy=-14, color=C["line"], fontWeight=600).encode(x="share:Q", y="expected_profit:Q", text="t:N"))
        st.altair_chart(layers.properties(height=330), width="stretch", theme="streamlit")
    with right:
        st.markdown("**Where the money goes at your capacity**")
        steps = [x for x in P.money(p, save, cost, offer) if x["step"] != "Offer cost" or offer > 0]
        run, out = 0.0, []
        for i, x in enumerate(steps):
            last = i == len(steps) - 1
            start, end = (0.0, x["amount"]) if last else (run, run + x["amount"])
            run = end
            out.append({**x, "start": start, "end": end, "kind": "Profit" if last else ("Kept" if x["amount"] >= 0 else "Cost"),
                        "text": ntd(x["amount"]), "tip": f"{x['amount']:,.0f}"})
        wf = pd.DataFrame(out)
        y = alt.Y("step:N", sort=None, title=None, axis=alt.Axis(labelLimit=140))
        bars = alt.Chart(wf).mark_bar(cornerRadius=4, size=26).encode(
            y=y, x=alt.X("start:Q", title="NT$ a month", axis=alt.Axis(format="~s")), x2="end:Q",
            color=alt.Color("kind:N", scale=alt.Scale(domain=["Kept", "Cost", "Profit"], range=[C["line"], C["you"], "#7fb2f0" if dark else "#1a5aa6"]),
                            legend=None),
            tooltip=[alt.Tooltip("step:N", title=""), alt.Tooltip("tip:N", title="NT$")])
        labels = alt.Chart(wf).transform_calculate(hi="max(datum.start, datum.end)").mark_text(align="left", dx=6, fontWeight=600, color=C["muted"]
            ).encode(y=y, x="hi:Q", text="text:N")
        st.altair_chart((bars + labels).properties(height=60 * len(wf) + 40), width="stretch", theme="streamlit")
        st.caption("Value kept = save rate × value at risk among the members called; costs are calls and offers.")
    st.caption(f"Forecast from calibrated churn chances for members expiring in March 2017, scored 14 days ahead. Profit = save rate × value at risk "
               f"− calls × cost − offer × saved members. **Backtest check** (members who actually churned, no offer cost): best at "
               f"{bt['share']:.1%} for {ntd(bt['profit'])}.")
    with st.expander("Table view"):
        st.dataframe(df[["label", "members_called", "expected_churners", "expected_value_at_risk", "expected_profit"]].rename(columns={
            "label": "Share", "members_called": "Members called", "expected_churners": "Likely churners", "expected_value_at_risk": "Value at risk (NT$)",
            "expected_profit": "Expected profit (NT$)"}), hide_index=True, width="stretch")

# 3. Demo members: filter, click one, see why
with members_tab:
    st.markdown("100 synthetic members (real member rows are not published), scored by the real model and ranked against the real cohort. "
                "**Click a point** or pick a member below.")
    a, b = st.columns([2, 1])
    risks = a.multiselect("Risk level", ["high", "medium", "low"], ["high", "medium", "low"], key="risks")
    only = b.toggle(f"Only inside your call list (top {p['share']:.1%})", False, key="only")
    dm = pd.DataFrame(P.demo_rows(snap, p["share"]))
    dm["churn_pct"] = dm["churn_chance"] * 100
    dm["list"] = dm["in_call_list"].map({True: "In your call list", False: "Not in your list"})
    view = dm[dm["risk"].isin(risks) & (dm["in_call_list"] | (not only))].sort_values("priority_percentile", ascending=False)
    st.caption(f"{len(view)} of {len(dm)} demo members shown; {int(dm['in_call_list'].sum())} are inside your call list.")

    if view.empty:
        st.info("No demo member matches these filters.")
    else:
        pick = alt.selection_point(fields=["member"], name="pick", on="click")
        scatter = alt.Chart(view).mark_point(filled=True, opacity=0.9, stroke="white", strokeWidth=0.8).encode(
            x=alt.X("churn_chance:Q", title="Chance of not renewing", axis=alt.Axis(format="%")),
            y=alt.Y("value_ntd:Q", title="Member value (NT$ a year)", scale=alt.Scale(zero=False)),
            size=alt.Size("value_at_risk_ntd:Q", title="Value at risk (NT$)", scale=alt.Scale(range=[70, 560])),
            color=alt.Color("risk:N", title="Risk", scale=alt.Scale(domain=["high", "medium", "low"], range=C["risk"])),
            shape=alt.Shape("list:N", title=None, scale=alt.Scale(domain=["In your call list", "Not in your list"], range=["circle", "diamond"])),
            tooltip=[alt.Tooltip("member:N", title="Member"), alt.Tooltip("churn_chance:Q", title="Churn chance", format=".0%"),
                     alt.Tooltip("value_ntd:Q", title="Value (NT$/yr)", format=","), alt.Tooltip("priority_percentile:Q", title="Ranks above (%)"),
                     alt.Tooltip("list:N", title="")]).add_params(pick)
        event = st.altair_chart(scatter.properties(height=360), width="stretch", theme="streamlit", on_select="rerun", key="scatter")
        clicked = [x.get("member") for x in (event.selection.get("pick") or [])] if event and getattr(event, "selection", None) else []
        if clicked and clicked[0] in set(view["member"]) and st.session_state.get("_last_click") != clicked[0]:
            st.session_state["member"], st.session_state["_last_click"] = clicked[0], clicked[0]
        if st.session_state.get("member") not in set(view["member"]):
            st.session_state.pop("member", None)

        mid = st.selectbox("Member to explain", view["member"].tolist(), key="member")
        e = snap["demo"][mid]["explanation"]; s = e["score"]
        st.subheader(f"{mid}: {s['churn_probability']:.0%} chance of not renewing ({s['risk_level']} risk), {ntd(s['member_value'])} a year at stake")
        k = st.columns(3)
        k[0].metric("Chance of not renewing", f"{s['churn_probability']:.0%}", f"{s['risk_level']} risk", delta_color="off", delta_arrow="off", border=True)
        k[1].metric("Value at stake", ntd(s["member_value"]), "12 months of revenue", delta_color="off", delta_arrow="off", border=True)
        k[2].metric("Priority", f"top {100 - s['priority_percentile']:.1f}%", "on churn chance × value", delta_color="off", delta_arrow="off", border=True)
        r = pd.DataFrame(e["reasons"]).assign(effect=lambda d: d["contribution"].map(lambda v: "Raises risk" if v > 0 else "Lowers risk"),
                                              text=lambda d: d["label"] + " (" + d["value"].astype(str) + ")")
        enc = {"y": alt.Y("text:N", sort=alt.EncodingSortField("contribution", op="max", order="descending"), title=None, axis=alt.Axis(labelLimit=320)),
               "x": alt.X("contribution:Q", title="Contribution to the model's score (log-odds)")}
        bars = alt.Chart(r).mark_bar(cornerRadiusEnd=4).encode(
            **enc, color=alt.Color("effect:N", scale=alt.Scale(domain=["Raises risk", "Lowers risk"], range=[C["raise"], C["lower"]]),
                                   legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("label:N", title="Reason"), alt.Tooltip("value:N", title="Value"), alt.Tooltip("contribution:Q", title="Log-odds", format="+.2f")])
        vals = alt.Chart(r).mark_text(align="left", dx=4, color=C["muted"]).encode(**enc, text=alt.Text("contribution:Q", format="+.2f"))
        st.markdown("**Why the model flags this member**")
        st.altair_chart((bars + vals).properties(height=alt.Step(30)), width="stretch", theme="streamlit")
        meter = e.get("meter", {})
        who = f"{meter.get('provider')} {meter.get('model')}" if meter.get("provider") != "template" else "the template writer"
        st.markdown(f"**Suggested action:** {e['suggested_action']}.")
        st.markdown(f"**Agent note** (written once offline by {who}; grader check: {'passed' if e.get('grounded') else 'failed'}; no model runs here):")
        st.html(f'<div class="note">{e["narrative"]}</div>')

# 4. The retention planner agent: recorded answers by default, live only with the viewer's own key
with agent_tab:
    import agent_tools as AT
    import chat
    st.markdown("Ask the retention planner agent (ADR-007) in plain words. It picks the tools (call list, what-if, a member's risk and "
                "reasons), reads their results and answers; every number must come from a tool.")
    chat.render(st, Path(__file__).resolve().parent / "replays.json", AT)

# 5. The live API: same plan, real HTTP
with api_tab:
    st.markdown(f"Run your plan against the public API ({API}). It answers from the same snapshot, so the numbers should match the plan tab "
                "(except the offer cost, which the API does not take).")
    q = {"share": round(p["share"], 3), "save_rate": save, "cost_per_call": float(cost)}
    url = f"{API}/call-list?{urllib.parse.urlencode(q)}"
    st.code(f"curl '{url}'", language="bash")
    if st.button("Run on the live API", key="run_api", type="primary"):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "churn-streamlit-app/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                got = json.load(resp)
            ms = (time.perf_counter() - t0) * 1000
            api_profit = got["summary"]["expected_profit"]
            same = api_profit == P.plan(grid, calls, save, cost, 0.0)["expected_profit"]
            st.success(f"Answered in {ms:,.0f} ms. API expected profit {ntd(api_profit)}; "
                       + ("matches this app (offer cost excluded)." if same else "differs from this app: the snapshot may have been rebuilt."))
            st.json(got["summary"])
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as err:
            st.warning(f"The API did not answer ({type(err).__name__}). It may be waking up or paused on the free tier; "
                       f"try again, or read the [results page]({P.PAGES}).")
    st.markdown("**Connect an AI assistant** (same four tools over MCP):")
    st.code(f"claude mcp add --transport http churn {P.API}/mcp", language="bash")
    st.markdown(f"Or install the [agent skill]({P.REPO}/blob/main/skills/churn-call-planner/SKILL.md), which reads these numbers with the right caveats.")
