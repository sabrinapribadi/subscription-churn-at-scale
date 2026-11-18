"""Streamlit companion app (R26, app template v2): overview, the data, a campaign plan, a member's reasons, the agent, the live API.

Only what the static results page cannot do; every number comes from the committed public snapshot, committed aggregate results
(data/outputs; no member rows) or the public API.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import frame as F  # noqa: E402  shared app frame (identical in every portfolio app)
import plan as P  # noqa: E402  sibling module; the app runs from the repo root on Streamlit Cloud

API = os.environ.get("CHURN_API_BASE", P.API)
OUT = P.ROOT / "data" / "outputs"
st.set_page_config(page_title="Churn call planner", page_icon=":material/call:", layout="wide", initial_sidebar_state="expanded")
F.setup(st, accent="#7fb2f0", title_font="'Space Grotesk',Inter,system-ui,sans-serif")

dark = getattr(getattr(st.context, "theme", None), "type", "light") == "dark"
C = {"line": "#4d94e8" if dark else "#2a78d6", "you": "#d95926" if dark else "#eb6834", "muted": "#8a93a3" if dark else "#6b7385",
     "raise": "#e66767" if dark else "#e34948", "lower": "#4d94e8" if dark else "#2a78d6",
     "risk": ["#f08a5d", "#c4562a", "#7a3a22"] if dark else ["#b8441a", "#eb6834", "#f6b896"]}   # high, medium, low: one orange ramp

PAGES = [
    F.Page("overview", "Overview", ":material/home:", "The results, the brief and where to start."),
    F.Page("explore", "Explore the data", ":material/query_stats:",
           "Who leaves (churn by expiry month, five listening groups), what the model weighs, and whether this month looks like the last. "
           "Aggregates only; no member rows."),
    F.Page("plan", "Plan a campaign", ":material/campaign:",
           "Your agents, calls and days give a call list; see how many likely leavers it reaches and what it is worth, net of call and offer costs."),
    F.Page("members", "Explain a member", ":material/person_search:",
           "100 synthetic members scored by the real model: why each is flagged, how they rank, and the suggested action."),
    F.Page("agent", "AI Assistant", ":material/smart_toy:",
           "Ask the retention planner in plain words: recorded answers replay for free with their tool calls; your own OpenAI key runs it live."),
    F.Page("api", "Live API and MCP", ":material/api:", "Run your plan on the public API and connect an AI assistant to the same tools."),
]
CAMPAIGN = ["agents", "per_day", "days", "save", "cost", "offer"]


@st.cache_data
def snapshot() -> dict:
    return P.load()


@st.cache_data
def committed(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def ntd(v: float) -> str:
    sign, v = ("−" if v < 0 else ""), abs(v)
    return f"{sign}NT${v / 1e6:.1f}M" if v >= 1e6 else f"{sign}NT${v:,.0f}"


snap = snapshot()
grid = snap["call_grid"]
hl = P.headline(snap)
F.keep(st, CAMPAIGN)
page = F.navigate(st, PAGES, brand="Churn call planner", tagline="Who to call before renewal, and what it is worth", icon="☏")
F.sidebar_stats(st, [(f"{hl['model_reach']:.0%}", f"leavers reached calling 10% (rule: {hl['rule_reach']:.0%})"),
                     (ntd(hl["profit_10pct"]), "backtest profit a month"), (f"{hl['members']:,}", "members scored"),
                     (f"{snap['notes']['grounded']}/{snap['notes']['live_calls']}", "agent notes pass the number check")])


def campaign() -> tuple[int, dict]:
    """Sidebar campaign inputs (plan, members and API pages); kept across pages."""
    with st.sidebar:
        F.sidebar_label(st, "Your campaign")
        agents = st.number_input("Call agents", 1, 2000, 50, key="agents")
        per_day = st.number_input("Calls per agent per day", 1, 300, 80, key="per_day")
        days = st.number_input("Working days before renewal", 1, 14, 10, key="days",
                               help="Members are scored 14 days before their plan expires, so about 10 working days.")
        save = st.slider("Save rate: share of called churners kept", 0.05, 0.50, 0.20, 0.01, format="%.2f", key="save",
                         help="An assumption, not data. A small call test measures it.")
        cost = st.slider("Cost per call (NT$)", 0, 100, 20, 1, key="cost")
        offer = st.slider("Retention offer per saved member (NT$)", 0, 500, 0, 10, key="offer",
                          help="Not in the API: the app subtracts offer × expected saved members.")
    calls = int(agents * per_day * days)
    return calls, {"agents": agents, "per_day": per_day, "days": days, "save": save, "cost": cost, "offer": offer}


def footer() -> None:
    F.sidebar_footer(st, {"Results page": P.PAGES, "Walkthrough": P.PAGES + "build.html", "Demo API": P.API + "/docs", "Source": P.REPO,
                          "Agent skill": P.REPO + "/blob/main/skills/churn-call-planner/SKILL.md"},
                     f"Data: KKBox public churn data (WSDM 2018), members expiring March 2017; model `{snap['model_version']}`, snapshot "
                     f"{snap['built']}. Member rows are never published.")


# 1. Overview: hero, KPI strip, the 5W1H brief and a card per page (R22, R26 item 7)
if page.key == "overview":
    footer()
    F.hero(st, f"KKBox public data · members expiring March 2017 · {grid['members']:,} members · amounts in NT$", "Churn call planner",
           "Who to call two weeks before renewal, and what a call campaign is worth with your team's capacity and costs.")
    F.kpis(st, [("Leavers reached, calling 10%", f"{hl['model_reach']:.0%}", f"today's rule: {hl['rule_reach']:.0%}"),
                ("Backtest profit a month", ntd(hl["profit_10pct"]), "March 2017, calling 10%"),
                ("Leavers the rule never calls", f"{hl['auto_per_100']:.0f} per 100", "auto-renew; the model calls"),
                ("Members scored", f"{hl['members']:,}", "14 days before expiry")])
    F.brief(st, F.load_brief(P.ROOT, P.REPO))
    F.links_line(st, {"Results page": P.PAGES, "Technical walkthrough": P.PAGES + "build.html", "Demo API": P.API + "/docs", "Source": P.REPO})
    F.use_cards(st, PAGES)

# 2. Explore the data: cohorts, listening groups, what the model weighs, drift (aggregates only)
elif page.key == "explore":
    footer()
    ds, beh, drv, dr = committed("p1_dataset.json"), committed("p3_behaviour.json"), committed("p8_global_drivers.json"), committed("p7_drift.json")
    months = pd.DataFrame([{"month": k.split(":")[1], **v} for k, v in ds.items() if k.startswith("k14_w120:")]).sort_values("month")
    months["label"] = months["month"].map(lambda m: pd.Timestamp(f"{m[:4]}-{m[4:]}-01").strftime("%b %Y"))
    gap = drv["rule_gap"]
    groups = pd.DataFrame(beh["personas"]).sort_values("churn_rate", ascending=False)
    names = {0: "Steady regulars", 1: "Silent payers", 2: "Re-engaging", 3: "Fading", 4: "Just came back"}   # ADR-003 names, by cluster
    groups["group"] = groups.apply(lambda r: f"{names[r['cluster']]} ({r['median_minutes_per_day']:.0f} min a day)", axis=1)
    themes = drv["themes"]
    top_theme = max(themes, key=lambda t: themes[t]["share_all"])
    mar = months[months["month"] == "201703"].iloc[0]
    feb = months[months["month"] == "201702"].iloc[0]
    agree = committed("p0_label_agreement.json")
    F.header(st, page, "Who leaves, and what does the model look at?",
             f"{mar['churn_rate']:.1%} of the {mar['members']:,} members expiring in {mar['label']} did not renew ({feb['churn_rate']:.1%} in "
             f"{feb['label']}; official labels). **{gap['auto_renew_share_of_leavers']:.0%} "
             f"of leavers had auto-renew on**, so a manual-renewal rule never calls them. {top_theme} signals carry "
             f"{themes[top_theme]['share_all']:.0%} of the model's attention, {themes[top_theme]['share_call_list']:.0%} inside the call list.")

    st.subheader("Churn by expiry month")
    st.altair_chart(alt.Chart(months).mark_bar(cornerRadiusEnd=4, size=38).encode(
        x=alt.X("label:N", sort=list(months["label"]), title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("churn_rate:Q", title="Did not renew", axis=alt.Axis(format="%")),
        color=alt.Color("label_source:N", title="Label", scale=alt.Scale(domain=["official", "reconstructed"], range=[C["line"], C["muted"]]),
                        legend=alt.Legend(orient="top")),
        tooltip=["label", alt.Tooltip("members:Q", format=","), alt.Tooltip("churn_rate:Q", format=".2%"), "label_source"]
    ).properties(height=260), width="stretch", theme="streamlit")
    st.caption(f"Official labels come with the dataset for Feb and Mar 2017. Earlier months use labels rebuilt from the transaction log with the "
               f"official rule; on the official months the rebuild matched {agree['2017-02']['label_agreement_on_overlap']:.1%} and "
               f"{agree['2017-03']['label_agreement_on_overlap']:.1%} of labels, short of the 99% gate (ADR-002), so the test uses official labels only.")

    st.subheader("Five listening groups (k-means on 60-day listening-shape statistics)")
    metric = st.segmented_control("Compare the groups on", ["Churn rate", "Their leavers reached by the top 10%", "Share of members"],
                                  default="Churn rate", key="group_metric") or "Churn rate"
    col = {"Churn rate": "churn_rate", "Their leavers reached by the top 10%": "reached_in_top10", "Share of members": "share"}[metric]
    st.altair_chart(alt.Chart(groups).mark_bar(cornerRadiusEnd=4, color=C["line"]).encode(
        y=alt.Y("group:N", sort=list(groups["group"]), title=None, axis=alt.Axis(labelLimit=300)),
        x=alt.X(f"{col}:Q", title=metric, axis=alt.Axis(format="%")),
        tooltip=["group", alt.Tooltip("members:Q", format=","), alt.Tooltip("churn_rate:Q", title="Churn rate", format=".1%"),
                 alt.Tooltip("reached_in_top10:Q", title="Leavers reached in top 10%", format=".0%"),
                 alt.Tooltip("median_tenure_days:Q", title="Median tenure (days)")]).properties(height=alt.Step(34)), width="stretch", theme="streamlit")
    st.caption("Names and clusters from ADR-003 (members expiring March 2017). The listening-shape features did not improve the model "
               "(+0.004 PR-AUC against a +0.02 bar), so the groups are kept for practitioners' messaging, not for scoring.")

    a, b = st.columns(2, gap="large")
    with a:
        st.markdown("**What the model weighs, by theme** (share of mean |TreeSHAP|)")
        th = pd.DataFrame([{"theme": t, "who": w, "share": v[k]} for t, v in themes.items()
                           for w, k in [("All members", "share_all"), ("Inside the call list", "share_call_list")]])
        st.altair_chart(alt.Chart(th).mark_bar(cornerRadiusEnd=3, height=11).encode(
            y=alt.Y("theme:N", sort=list(themes), title=None, axis=alt.Axis(labelLimit=200)), yOffset="who:N",
            x=alt.X("share:Q", title=None, axis=alt.Axis(format="%")),
            color=alt.Color("who:N", scale=alt.Scale(range=[C["muted"], C["line"]]), legend=alt.Legend(title=None, orient="top")),
            tooltip=["theme", "who", alt.Tooltip("share:Q", format=".0%")]).properties(height=alt.Step(30)), width="stretch", theme="streamlit")
    with b:
        n = st.slider("Top features", 5, 20, 10, key="nfeat")
        feats = pd.DataFrame(drv["features"]).sort_values("share_all", ascending=False).head(n)
        st.markdown(f"**The {n} features the model leans on most**")
        st.altair_chart(alt.Chart(feats).mark_bar(cornerRadiusEnd=3, color=C["line"]).encode(
            y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)), x=alt.X("share_all:Q", title=None, axis=alt.Axis(format="%")),
            tooltip=["label", alt.Tooltip("share_all:Q", title="All members", format=".1%"),
                     alt.Tooltip("share_call_list:Q", title="Call list", format=".1%")]).properties(height=alt.Step(24)), width="stretch", theme="streamlit")

    st.subheader(f"Is March like February? Input drift (PSI) on {dr['features_checked']} features and the score")
    tb = pd.DataFrame(dr["table"]).sort_values("psi", ascending=False)
    clip = st.toggle("Clip the scale at 0.5 (shows the stable features)", True, key="clip")
    tb["shown"] = tb["psi"].clip(upper=0.5) if clip else tb["psi"]
    st.altair_chart((alt.Chart(tb).mark_bar(cornerRadiusEnd=3).encode(
        y=alt.Y("feature:N", sort=list(tb["feature"]), title=None, axis=alt.Axis(labelLimit=220)), x=alt.X("shown:Q", title="PSI"),
        color=alt.Color("band:N", scale=alt.Scale(domain=["stable", "watch", "alert"], range=[C["muted"], "#e0b04d", C["raise"]]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=["feature", alt.Tooltip("psi:Q", format=".3f"), "band", "reference_mean", "current_mean"])
        + alt.Chart(pd.DataFrame([{"x": dr["alert_threshold"]}])).mark_rule(strokeDash=[4, 3], color=C["muted"]).encode(x="x:Q")
    ).properties(height=alt.Step(22)), width="stretch", theme="streamlit")
    st.caption(f"Dashed line: alert at PSI {dr['alert_threshold']}. {dr['bands']['alert']} features alert ({', '.join(dr['alerts'])}); the score itself "
               f"moved by PSI {dr['score_psi']}. Lagged check: the list expected {dr['lagged']['expected_churners_on_list']:,.0f} leavers and "
               f"{dr['lagged']['realised_churners_on_list']:,} left.")

# 3. Plan a campaign with your own capacity and costs
elif page.key == "plan":
    calls, cfg = campaign()
    footer()
    save, cost, offer = cfg["save"], cfg["cost"], cfg["offer"]
    p = P.plan(grid, calls, save, cost, offer)
    rows = P.curve(grid, save, cost, offer)
    top = P.best(rows)
    bt = P.backtest_best(snap["scenarios"], save, cost)
    F.header(st, page, "How many members should we call with our team, and what is it worth?",
             f"Your {calls:,} calls cover the top {p['share']:.1%} and reach about {p['expected_churners']:,.0f} likely leavers: expected profit "
             f"**{ntd(p['expected_profit'])} a month**. The most profitable list at these costs is the top {top['share']:.1%} "
             f"({ntd(top['expected_profit'])}). Change the campaign in the sidebar.")
    st.subheader(f"Calling the top {p['share']:.1%} (about {p['members_called']:,} members) reaches about {p['expected_churners']:,.0f} "
                 f"likely churners; expected profit {ntd(p['expected_profit'])} a month")
    st.caption(f"Your capacity: {cfg['agents']:,} agents × {cfg['per_day']:,} calls × {cfg['days']} days = {calls:,} calls, rounded to the nearest "
               "0.1% of members (the snapshot's grid, as in the API). Change it in the sidebar.")
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
        labels = alt.Chart(wf).transform_calculate(hi="max(datum.start, datum.end)").mark_text(
            align="left", dx=6, fontWeight=600, color=C["muted"]).encode(y=y, x="hi:Q", text="text:N")
        st.altair_chart((bars + labels).properties(height=60 * len(wf) + 40), width="stretch", theme="streamlit")
        st.caption("Value kept = save rate × value at risk among the members called; costs are calls and offers.")
    st.caption(f"Forecast from calibrated churn chances for members expiring in March 2017, scored 14 days ahead. Profit = save rate × value at risk "
               f"− calls × cost − offer × saved members. **Backtest check** (members who actually churned, no offer cost): best at "
               f"{bt['share']:.1%} for {ntd(bt['profit'])}.")
    with st.expander("Table view"):
        st.dataframe(df[["label", "members_called", "expected_churners", "expected_value_at_risk", "expected_profit"]].rename(columns={
            "label": "Share", "members_called": "Members called", "expected_churners": "Likely churners", "expected_value_at_risk": "Value at risk (NT$)",
            "expected_profit": "Expected profit (NT$)"}), hide_index=True, width="stretch")

# 4. Explain a member: filter, click one, see why
elif page.key == "members":
    calls, cfg = campaign()
    footer()
    p = P.plan(grid, calls, cfg["save"], cfg["cost"], cfg["offer"])
    top_box = st.container()                                    # the header is filled once the member is chosen
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
        F.header(top_box, page, "Why is this member on the call list, and what should the agent do?", "No demo member matches these filters.")
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
        e = snap["demo"][mid]["explanation"]
        s = e["score"]
        up = [x for x in e["reasons"] if x["contribution"] > 0]
        F.header(top_box, page, "Why is this member on the call list, and what should the agent do?",
                 f"{mid}: {s['churn_probability']:.0%} chance of not renewing, {ntd(s['member_value'])} a year at stake, top "
                 f"{100 - s['priority_percentile']:.1f}% on priority. "
                 + (f"The strongest reason is **{up[0]['label']} ({up[0]['value']})**. " if up else "")
                 + f"Suggested action: {e['suggested_action']}.")
        st.subheader(f"{mid}: {s['churn_probability']:.0%} chance of not renewing ({s['risk_level']} risk), {ntd(s['member_value'])} a year at stake")
        k = st.columns(3)
        k[0].metric("Chance of not renewing", f"{s['churn_probability']:.0%}", f"{s['risk_level']} risk", delta_color="off", delta_arrow="off", border=True)
        k[1].metric("Value at stake", ntd(s["member_value"]), "12 months of revenue", delta_color="off", delta_arrow="off", border=True)
        k[2].metric("Priority", f"top {100 - s['priority_percentile']:.1f}%", "on churn chance × value", delta_color="off", delta_arrow="off", border=True)
        r = pd.DataFrame(e["reasons"]).assign(effect=lambda d: d["contribution"].map(lambda v: "Raises risk" if v > 0 else "Lowers risk"),
                                              text=lambda d: d["label"] + " (" + d["value"].astype(str) + ")")
        enc = {"y": alt.Y("text:N", sort=alt.EncodingSortField("contribution", op="max", order="descending"), title=None, axis=alt.Axis(labelLimit=320)),
               "x": alt.X("contribution:Q", title="How hard each reason pushes the churn chance (longer = stronger)", axis=alt.Axis(labels=False))}
        bars = alt.Chart(r).mark_bar(cornerRadiusEnd=4).encode(
            **enc, color=alt.Color("effect:N", scale=alt.Scale(domain=["Raises risk", "Lowers risk"], range=[C["raise"], C["lower"]]),
                                   legend=alt.Legend(title=None, orient="top")),
            tooltip=[alt.Tooltip("label:N", title="Reason"), alt.Tooltip("value:N", title="Value"), alt.Tooltip("effect:N", title="")])
        vals = alt.Chart(r).mark_text(align="left", dx=4, color=C["muted"]).encode(**enc, text="effect:N")
        st.markdown("**Why the model flags this member**")
        st.altair_chart((bars + vals).properties(height=alt.Step(30)), width="stretch", theme="streamlit")
        meter = e.get("meter", {})
        who = f"{meter.get('provider')} {meter.get('model')}" if meter.get("provider") != "template" else "the template writer"
        st.markdown(f"**Suggested action:** {e['suggested_action']}.")
        st.markdown(f"**Agent note** (written once offline by {who}; grader check: {'passed' if e.get('grounded') else 'failed'}; no model runs here):")
        st.html(f'<div class="f-note">{e["narrative"]}</div>')

# 5. AI Assistant: recorded answers by default, live only with the viewer's own key
elif page.key == "agent":
    footer()
    import agent_tools as AT
    import chat
    rec = json.loads((HERE / "replays.json").read_text())["runs"]
    F.header(st, page, "Can a retention manager ask in plain words instead of reading charts?",
             f"Yes. The planner agent (ADR-007) picks the tools (call list, what-if, a member's risk and reasons) and answers; every number must "
             f"come from a tool. {sum(r['grounded'] for r in rec)} of {len(rec)} recorded answers pass that check. Replay is free; with your own "
             "OpenAI key you can ask anything, 10 questions per session, and the key is never stored.")
    chat.render(st, HERE / "replays.json", AT)

# 6. Live API and MCP: same plan, real HTTP
elif page.key == "api":
    calls, cfg = campaign()
    footer()
    save, cost = cfg["save"], cfg["cost"]
    p = P.plan(grid, calls, save, cost, cfg["offer"])
    F.header(st, page, "Can our own tools get the same numbers?",
             f"Yes: the public API answers from the same snapshot, so the plan for your {calls:,} calls should match this app's expected profit "
             "(the API takes no offer cost). The same four tools are served over MCP for AI assistants.")
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
