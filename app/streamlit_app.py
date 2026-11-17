"""Streamlit companion app (R26): plan a call campaign with your own capacity, explore the demo members, call the live API.

Only what the static results page cannot do; every number comes from the committed public snapshot or the public API.
Run: streamlit run app/streamlit_app.py
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
st.set_page_config(page_title="Churn call planner", layout="wide")

dark = getattr(getattr(st.context, "theme", None), "type", "light") == "dark"
C = {"line": "#3987e5" if dark else "#2a78d6", "you": "#d95926" if dark else "#eb6834",
     "raise": "#e66767" if dark else "#e34948", "lower": "#3987e5" if dark else "#2a78d6"}


@st.cache_data
def snapshot() -> dict:
    return P.load()


snap, ntd = snapshot(), (lambda v: f"NT${v / 1e6:.1f}M" if abs(v) >= 1e6 else f"NT${v:,.0f}")
grid = snap["call_grid"]

# 1. Brief first (R22, R26)
st.title("Churn call planner")
st.caption(f"Model {snap['model_version']} · snapshot built {snap['built']} · amounts in New Taiwan dollars (NT$)")
with st.container(border=True):
    for w, lines in P.brief():
        st.markdown(f"**{w}:** " + " ".join(lines))
st.markdown(f"[Results page]({P.PAGES}) · [Technical walkthrough]({P.PAGES}build.html) · [Demo API]({P.API}/docs) · [Source]({P.REPO})")
st.info("Free Streamlit Community Cloud app: it sleeps after 12 hours without visits, and the first visit wakes it (up to a minute). "
        f"The [results page]({P.PAGES}) is always on and carries every result.")

plan_tab, members_tab, api_tab = st.tabs(["Plan a campaign", "Explore demo members", "Ask the live API"])

# 2. Plan with your own capacity and costs
with plan_tab:
    st.markdown("Size a call campaign from your team's capacity. Members are called in model order: churn chance × member value.")
    a, b, c = st.columns(3)
    agents = a.number_input("Call agents", 1, 2000, 50, key="agents")
    per_day = b.number_input("Calls per agent per day", 1, 300, 80, key="per_day")
    days = c.number_input("Working days before renewal", 1, 14, 10, key="days",
                          help="Members are scored 14 days before their plan expires, so about 10 working days.")
    a, b, c = st.columns(3)
    save = a.slider("Save rate: share of called churners kept", 0.05, 0.50, 0.20, 0.01, format="%.2f", key="save",
                    help="An assumption, not data. A small call test measures it.")
    cost = b.slider("Cost per call (NT$)", 0, 100, 20, 1, key="cost")
    offer = c.slider("Retention offer per saved member (NT$)", 0, 500, 0, 10, key="offer",
                     help="Not in the API: the app subtracts offer × expected saved members.")

    calls = int(agents * per_day * days)
    p = P.plan(grid, calls, save, cost, offer)
    rows = P.curve(grid, save, cost, offer)
    top = P.best(rows)
    bt = P.backtest_best(snap["scenarios"], save, cost)
    capped = calls < top["members_called"]

    st.subheader(f"Calling the top {p['share']:.1%} (about {p['members_called']:,} members) reaches about {p['expected_churners']:,.0f} "
                 f"likely churners; expected profit {ntd(p['expected_profit'])} a month")
    st.caption(f"Your capacity: {agents:,} agents × {per_day:,} calls × {days} days = {calls:,} calls, rounded to the nearest 0.1% of members "
               "(the snapshot's grid, as in the API).")
    m = st.columns(4)
    m[0].metric("Members called", f"{p['members_called']:,}", f"top {p['share']:.1%} of {grid['members']:,}", delta_color="off", delta_arrow="off")
    m[1].metric("Likely churners reached", f"{p['expected_churners']:,.0f}", f"{p['expected_saved']:,.0f} kept at your save rate", delta_color="off", delta_arrow="off")
    m[2].metric("Value at risk among them", ntd(p["expected_value_at_risk"]), "12 months of revenue", delta_color="off", delta_arrow="off")
    m[3].metric("Expected profit", ntd(p["expected_profit"]), "after calls and offers", delta_color="off", delta_arrow="off")
    if p["expected_profit"] <= 0:
        st.warning("At these costs the campaign loses money: call fewer members, cut the offer, or test whether the save rate is higher.")
    elif capped:
        st.markdown(f"- **Capacity is the limit:** profit keeps rising to the top {top['share']:.1%} (about {top['members_called']:,} calls, "
                    f"{ntd(top['expected_profit'])}). More agents or days would pay.")
    else:
        st.markdown(f"- **You have more capacity than pays:** the best is the top {top['share']:.1%} (about {top['members_called']:,} calls, "
                    f"{ntd(top['expected_profit'])}); calls beyond it cost more than they keep.")
    st.markdown(f"- **Backtest check** (March 2017 members who actually churned, no offer cost): best at {bt['share']:.1%} for {ntd(bt['profit'])}.")

    df = pd.DataFrame(rows).assign(label=lambda d: d["share"].map(lambda s: f"{s:.1%}"))
    base = alt.Chart(df).encode(x=alt.X("share:Q", title="Share of members called", axis=alt.Axis(format="%")))
    line = base.mark_line(color=C["line"], strokeWidth=2).encode(y=alt.Y("expected_profit:Q", title="Expected profit (NT$)", axis=alt.Axis(format="~s")))
    hover = base.mark_point(size=80, opacity=0, color=C["line"]).encode(
        y="expected_profit:Q", tooltip=[alt.Tooltip("label:N", title="Share"), alt.Tooltip("members_called:Q", title="Members called", format=","),
                                        alt.Tooltip("expected_profit:Q", title="Expected profit (NT$)", format=",.0f")])
    you = alt.Chart(pd.DataFrame([{"share": p["share"], "t": f"your capacity: {p['share']:.1%}"}])).mark_rule(color=C["you"], strokeWidth=2, strokeDash=[4, 3]
        ).encode(x="share:Q", tooltip=alt.Tooltip("t:N", title=""))
    you_lbl = alt.Chart(pd.DataFrame([{"share": p["share"], "y": df["expected_profit"].max(), "t": "your capacity"}])).mark_text(
        align="left", dx=6, dy=-6, color=C["you"]).encode(x="share:Q", y="y:Q", text="t:N")
    peak = alt.Chart(pd.DataFrame([top])).mark_point(size=90, filled=True, color=C["line"]).encode(x="share:Q", y="expected_profit:Q")
    peak_lbl = alt.Chart(pd.DataFrame([{**top, "t": f"best: {top['share']:.1%}"}])).mark_text(dy=-12, color=C["line"]).encode(
        x="share:Q", y="expected_profit:Q", text="t:N")
    st.altair_chart((line + hover + you + you_lbl + peak + peak_lbl).properties(height=320), use_container_width=True, theme="streamlit")
    st.caption("Forecast from calibrated churn chances for members expiring in March 2017 (862,158), scored 14 days ahead. "
               "Profit = save rate × value at risk − calls × cost − offer × saved members.")
    with st.expander("Table view"):
        st.dataframe(df[["label", "members_called", "expected_churners", "expected_value_at_risk", "expected_profit"]].rename(columns={
            "label": "Share", "members_called": "Members called", "expected_churners": "Likely churners", "expected_value_at_risk": "Value at risk (NT$)",
            "expected_profit": "Expected profit (NT$)"}), hide_index=True, use_container_width=True)

# 3. Demo members: filter, pick one, see why
with members_tab:
    st.markdown("100 synthetic members (real member rows are not published) scored by the real model and ranked against the real cohort.")
    a, b = st.columns([2, 1])
    risks = a.multiselect("Risk level", ["high", "medium", "low"], ["high", "medium", "low"], key="risks")
    only = b.toggle(f"Only inside your call list (top {p['share']:.1%})", False, key="only")
    dm = pd.DataFrame(P.demo_rows(snap, p["share"]))
    dm["churn_chance"] = dm["churn_chance"] * 100
    view = dm[dm["risk"].isin(risks) & (dm["in_call_list"] | (not only))].sort_values("priority_percentile", ascending=False)
    st.caption(f"{len(view)} of {len(dm)} demo members shown; {int(dm['in_call_list'].sum())} are inside your call list.")
    st.dataframe(view.rename(columns={"member": "Member", "churn_chance": "Churn chance", "risk": "Risk", "value_ntd": "Value (NT$/yr)",
                                      "value_at_risk_ntd": "Value at risk (NT$)", "priority_percentile": "Ranks above (%)", "in_call_list": "In your list"}),
                 hide_index=True, use_container_width=True, height=240,
                 column_config={"Churn chance": st.column_config.NumberColumn(format="%.0f%%"),
                                "Value (NT$/yr)": st.column_config.NumberColumn(format="localized"),
                                "Value at risk (NT$)": st.column_config.NumberColumn(format="localized"),
                                "Ranks above (%)": st.column_config.NumberColumn(format="%.1f")})
    if view.empty:
        st.info("No demo member matches these filters.")
    else:
        mid = st.selectbox("Member to explain", view["member"].tolist(), key="member")
        e = snap["demo"][mid]["explanation"]; s = e["score"]
        st.subheader(f"{mid}: {s['churn_probability']:.0%} chance of not renewing ({s['risk_level']} risk), {ntd(s['member_value'])} a year at stake")
        r = pd.DataFrame(e["reasons"]).assign(effect=lambda d: d["contribution"].map(lambda v: "Raises risk" if v > 0 else "Lowers risk"),
                                              text=lambda d: d["label"] + " (" + d["value"].astype(str) + ")")
        enc = {"y": alt.Y("text:N", sort=alt.EncodingSortField("contribution", op="max", order="descending"), title=None,
                          axis=alt.Axis(labelLimit=320)),
               "x": alt.X("contribution:Q", title="Contribution to the model's score (log-odds)")}
        bars = alt.Chart(r).mark_bar(cornerRadiusEnd=4).encode(
            **enc, color=alt.Color("effect:N", scale=alt.Scale(domain=["Raises risk", "Lowers risk"], range=[C["raise"], C["lower"]]),
                                   legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("label:N", title="Reason"), alt.Tooltip("value:N", title="Value"), alt.Tooltip("contribution:Q", title="Log-odds", format="+.2f")])
        vals = alt.Chart(r).mark_text(align="left", dx=4).encode(**enc, text=alt.Text("contribution:Q", format="+.2f"),
                                                                  color=alt.value("#898781"))
        st.altair_chart((bars + vals).properties(height=alt.Step(30)), use_container_width=True, theme="streamlit")
        st.markdown(f"- **Suggested action:** {e['suggested_action']}.\n"
                    f"- **Priority:** ranks above {s['priority_percentile']:.1f}% of real members on churn chance × value.")
        meter = e.get("meter", {})
        who = f"{meter.get('provider')} {meter.get('model')}" if meter.get("provider") != "template" else "the template writer"
        st.markdown(f"**Agent note** (written once offline by {who}; grader check: {'passed' if e.get('grounded') else 'failed'}; no model runs here):")
        st.markdown(f"> {e['narrative']}")

# 4. The live API: same plan, real HTTP
with api_tab:
    st.markdown(f"Run your plan against the public API ({API}). It answers from the same snapshot, so the numbers should match the plan tab "
                "(except the offer cost, which the API does not take).")
    q = {"share": round(p["share"], 3), "save_rate": save, "cost_per_call": float(cost)}
    url = f"{API}/call-list?{urllib.parse.urlencode(q)}"
    st.code(f"curl '{url}'", language="bash")
    if st.button("Run on the live API", key="run_api"):
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
