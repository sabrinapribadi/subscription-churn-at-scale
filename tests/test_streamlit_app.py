"""Streamlit companion app (R26): logic against the snapshot, and AppTest smoke tests of the page (offline)."""
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


def test_brief_links_are_absolute():
    items = dict(P.brief())
    assert {"What", "Why", "Who", "Where", "How"} <= set(items)
    assert "](skills/" not in " ".join(items["Where"]) and P.REPO + "/blob/main/skills/" in " ".join(items["Where"])


def run(**state):
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    for k, v in state.items():
        (at.number_input(key=k) if k in {"agents", "per_day", "days"} else at.slider(key=k)).set_value(v)
    at.run()
    assert not at.exception, at.exception
    return at


def test_page_opens_with_brief_limits_and_plan():
    at = run()
    text = " ".join(m.value for m in at.markdown)
    assert "**What:**" in text and "Results page" in text and "Technical walkthrough" in text
    assert "12 hours" in at.info[0].value                                 # free-tier limits stated (R26)
    assert at.subheader[0].value.startswith("Calling the top 4.6%")      # 50 agents × 80 calls × 10 days = 40,000 calls
    assert any("= 40,000 calls" in c.value for c in at.caption)
    assert [m.label for m in at.metric] == ["Members called", "Likely churners reached", "Value at risk among them", "Expected profit"]


def test_capacity_and_loss_messages():
    at = run(agents=500)                                                  # 400,000 calls: beyond the best share
    assert any("more capacity than pays" in m.value for m in at.markdown)
    at = run(cost=100, save=0.05)
    assert at.warning and "loses money" in at.warning[0].value


def test_member_explorer_and_api_failure_is_handled(monkeypatch):
    monkeypatch.setenv("CHURN_API_BASE", "http://127.0.0.1:9")            # nothing listens: the button must warn, not crash
    at = run()
    at.selectbox(key="member").set_value("demo-001").run()
    assert any(s.value.startswith("demo-001: 17% chance") for s in at.subheader)
    at.button(key="run_api").click().run()
    assert not at.exception and any("did not answer" in w.value for w in at.warning)
