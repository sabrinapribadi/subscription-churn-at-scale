"""Streamlit companion app (R26): logic against the snapshot, and AppTest smoke tests of the page (offline)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import plan as P

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(ROOT / "app" / "streamlit_app.py")


def test_plan_matches_public_api_formula():
    snap = P.load(); g = snap["call_grid"]
    p = P.plan(g, 86215, 0.20, 20)                                     # top 10%: the figures the live check pins
    assert p["members_called"] == 86215 and p["expected_profit"] == 10459431.0
    assert P.plan(g, 86215, 0.20, 20, offer=100)["expected_profit"] == round(10459431.0 - 100 * 0.20 * 33807.7, 0)
    assert round(P.best(P.curve(g, 0.25, 15))["share"], 3) == 0.26        # the skill's forecast best share
    assert P.backtest_best(snap["scenarios"], 0.20, 20)["share"] == 0.195  # equals the API's what-if best_share


def test_money_breakdown_sums_to_profit():
    g = P.load()["call_grid"]
    p = P.plan(g, 40000, 0.20, 20, offer=50)
    m = P.money(p, 0.20, 20, 50)
    assert abs(sum(x["amount"] for x in m[:3]) - m[3]["amount"]) < 1


def test_brief_links_are_absolute():
    items = dict(P.brief())
    assert {"What", "Why", "Who", "Where", "How"} <= set(items)
    assert "](skills/" not in " ".join(items["Where"]) and P.REPO + "/blob/main/skills/" in " ".join(items["Where"])


PAGES = ["overview", "explore", "plan", "members", "agent", "api"]


def run(page="plan", **state):
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["page"] = page
    at.run()
    for k, v in state.items():
        (at.number_input(key=k) if k in {"agents", "per_day", "days"} else at.slider(key=k)).set_value(v)
    at.run()
    assert not at.exception, at.exception
    return at


def html_text(at) -> str:
    return " ".join(e.proto.body for e in at.get("html"))


def test_first_screen_brief_limits_and_pages():
    at = run("overview")
    text = " ".join(m.value for m in at.markdown)
    caps = " ".join(c.value for c in at.caption)
    assert "A churn early warning" in text and "Results page" in caps and "Technical walkthrough" in caps
    assert "12 hours" in caps                                             # free-tier limits stated (R26)
    labels = [m.label for m in at.metric]
    assert labels[:4] == ["Leavers reached, calling 10%", "Backtest profit a month", "Leavers the rule never calls", "Members scored"]
    assert [m.value for m in at.metric][:2] == ["65%", "NT$12.4M"]       # first screen: committed results, as the API reports
    for w in ["What", "Why", "Who", "Where", "When it fails", "How"]:     # the 5W1H brief (R22)
        assert f'class="f-w">{w}<' in html_text(at), w
    assert [b.key for b in at.sidebar.button] == [f"nav_{k}" for k in PAGES]


def test_every_page_opens_with_its_business_question():
    for key in PAGES[1:]:
        at = run(key)
        assert "Business question" in html_text(at), key


def test_plan_page_and_campaign_kept_across_pages():
    at = run()
    assert at.subheader[0].value.startswith("Calling the top 4.6%")      # 50 agents × 80 calls × 10 days = 40,000 calls
    assert any("= 40,000 calls" in c.value for c in at.caption)
    assert [m.label for m in at.metric][:4] == ["Members called", "Likely churners", "Value at risk", "Expected profit"]
    at.number_input(key="agents").set_value(100).run()
    at.sidebar.button(key="nav_overview").click().run()
    at.sidebar.button(key="nav_plan").click().run()
    assert not at.exception and at.number_input(key="agents").value == 100


def test_explore_uses_official_months_and_named_groups():
    at = run("explore")
    page = html_text(at)
    assert "7.3% of the 862,158 members expiring in Mar 2017" in page and "5.5% in Feb 2017" in page
    assert any("98.8%" in c.value and "97.0%" in c.value for c in at.caption)


def test_capacity_and_loss_messages():
    at = run(agents=500)                                                  # 400,000 calls: beyond the best share
    assert any("more capacity than pays" in m.value for m in at.info)
    assert any("Capacity is the limit" in m.value for m in run().success)
    at = run(cost=100, save=0.05)
    assert at.warning and "loses money" in at.warning[0].value


def test_member_explorer_and_api_failure_is_handled(monkeypatch):
    monkeypatch.setenv("CHURN_API_BASE", "http://127.0.0.1:9")            # nothing listens: the button must warn, not crash
    at = run("members")
    at.selectbox(key="member").set_value("demo-001").run()
    assert any(s.value.startswith("demo-001: 17% chance") for s in at.subheader)
    at = run("api")
    at.button(key="run_api").click().run()
    assert not at.exception and any("did not answer" in w.value for w in at.warning)


# ---------------------------------------------------------------- chat tab (replay by default, live with the viewer's key)
import agent as A
import agent_tools as AT

REPLAYS = json.loads((ROOT / "app" / "replays.json").read_text())


def test_replays_recorded_grounded_and_keyless():
    runs = REPLAYS["runs"]
    assert [r["question"] for r in runs] == AT.QUESTIONS
    assert all(r["grounded"] for r in runs) and REPLAYS["summary"]["cost_per_1000_usd"] < 1.0
    raw = (ROOT / "app" / "replays.json").read_text()
    assert "sk-" not in raw and "OPENAI" not in raw
    for r in runs:                                                     # the stored flag agrees with today's checker
        assert A.ungrounded_numbers(r["answer"], [r["question"], r["tool_results"]]) == r["ungrounded_numbers"]


def test_grader_and_matching():
    assert A.ungrounded_numbers("elevation 2 m, 185% more, below 25 Mbps, 16.8M", [{"chance_below_25_mbps": 0, "g": 1.853, "e": 2, "p": 16.84e6}]) == []
    assert A.ungrounded_numbers("profit 999,999", [{"p": 5}]) == ["999,999"]
    best, score = A.closest(AT.QUESTIONS[0].lower().replace("?", ""), REPLAYS["runs"])
    assert best["question"] == AT.QUESTIONS[0] and score > 0.8
    assert A.closest("zzzz qqqq", REPLAYS["runs"])[1] < 0.35
    fake = "sk" + "-" + "abcdefghijk123"                                   # built at runtime: no key-shaped string in the repo
    assert A.redact(f"bad key {fake} rejected", fake) == "bad key [your key] rejected"


def _chat_app(monkeypatch, fake_run=None):
    if fake_run:
        monkeypatch.setattr(A, "run", fake_run)
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["page"] = "agent"
    at.run()
    assert not at.exception, at.exception
    return at


def test_chat_replay_default(monkeypatch):
    at = _chat_app(monkeypatch)
    assert at.radio(key="chat_mode").value.startswith("Replay")
    at.selectbox(key="replay_pick").set_value(AT.QUESTIONS[0]).run()
    assert not at.exception and any(REPLAYS["runs"][0]["answer"][:40] in m.value for m in at.markdown)


def test_chat_live_uses_viewer_key_and_never_echoes_it(monkeypatch):
    key = "sk" + "-" + "test-viewerkey-123456"                               # fake, built at runtime
    seen = {}

    def fake(q, client, tools, system, model, prices, **kw):
        seen["key"] = client.api_key
        return {"question": q, "answer": "Live answer.", "tool_calls": [], "tool_results": [], "steps": 1, "grounded": True,
                "ungrounded_numbers": [], "model": model, "tokens": {"input": 10, "cached_input": 0, "output": 5}, "cost_usd": 1e-6, "latency_ms": 5.0}
    at = _chat_app(monkeypatch, fake)
    at.radio(key="chat_mode").set_value("Live: use your own OpenAI key").run()
    at.text_input(key="byo_key").input(key).run()
    at.chat_input(key="live_input").set_value("Anything").run()
    assert seen["key"] == key and any("Live answer." in m.value for m in at.markdown)
    assert key not in " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)

    def boom(*a, **k):
        raise RuntimeError(f"Incorrect API key provided: {key}")
    at = _chat_app(monkeypatch, boom)
    at.radio(key="chat_mode").set_value("Live: use your own OpenAI key").run()
    at.text_input(key="byo_key").input(key).run()
    at.chat_input(key="live_input").set_value("Anything").run()
    assert at.error and key not in at.error[0].value and "[your key]" in at.error[0].value


def test_app_agent_matches_repo_agent():
    """The app's agent is the repo's planner: same instructions, same tool schemas (src needs the serving packages)."""
    agent_mod = pytest.importorskip("src.genai.agent")
    tools_mod = pytest.importorskip("src.genai.tools")
    assert AT.SYSTEM == agent_mod.SYSTEM
    assert AT.SCHEMAS == json.loads(json.dumps(tools_mod.openai_tool_schemas(tools_mod.build_tools(None))))


def test_frame_is_the_shared_copy():
    """The app frame is identical in every portfolio app; change it everywhere at once (checksum of the shared copy)."""
    import hashlib
    assert hashlib.sha256((ROOT / "app" / "frame.py").read_bytes()).hexdigest()[:16] == "385e92329f20405a"
