"""Agent skill client (R24): argument handling, request building and the three charts, with the network stubbed out."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "skills/churn-call-planner"
SPEC = importlib.util.spec_from_file_location("churn_client", ROOT / "scripts/churn.py")
churn = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(churn)

ROOT_INFO = {"model_version": "lgbm-test", "cohort_members": 862158, "data_terms": "aggregates only", "results_page": "x"}
EXPLAIN = {"member_id": "demo-001",
           "score": {"churn_probability": 0.1739, "risk_level": "medium", "member_value": 1812.8, "priority_percentile": 89.49},
           "reasons": [{"label": "days since last payment", "value": "38", "contribution": 1.13},
                       {"label": "payment method", "value": "type 36", "contribution": 0.715},
                       {"label": "auto-renew", "value": "on", "contribution": -0.2001}],
           "suggested_action": "send a re-engagement message"}


def fake(path, params):
    if path == "/":
        return ROOT_INFO
    if path == "/call-list":
        s, r = params["share"], params["save_rate"]          # profit peaks later at higher save rates, as in the real curve
        k, ev = 862158 * s, 1.2e8 * (1 - (1 - s) ** 4)
        return {"summary": {"members_called": round(k), "expected_churners": 0.5 * k, "expected_value_at_risk": ev,
                            "expected_profit": round(r * ev - params["cost_per_call"] * k)}}
    if path == "/what-if":
        return {"profit_at_10pct": {"probability": 12408440.0, "expected_value": 12431421.0, "lambdamart": 9699147.0},
                "best_share": 0.34, "best_monthly_profit": 19471247.0}
    return EXPLAIN


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(churn, "get", lambda base, path, params=None, timeout=60: seen.append((path, params)) or fake(path, params))
    return seen


def test_routes(calls, capsys):
    churn.main(["call-list", "--share", "0.058", "--save-rate", "0.25", "--cost", "15"])
    churn.main(["what-if"]); churn.main(["score", "demo-001"]); churn.main(["explain", "a/b"])
    assert calls == [("/call-list", {"share": 0.058, "save_rate": 0.25, "cost_per_call": 15.0}),
                     ("/what-if", {"save_rate": 0.2, "cost_per_call": 20.0}),
                     ("/members/demo-001/score", None), ("/members/a%2Fb/explanation", None)]   # ids are quoted, never spliced
    assert capsys.readouterr().out.count("{") >= 4


def test_bad_share(calls):
    with pytest.raises(SystemExit):
        churn.main(["call-list", "--share", "1.5"])
    assert calls == []


def test_about_states_period_and_assumptions(calls):
    ab = churn.about("x")
    assert ab["test_cohort"]["members"] == 862158 and "March 2017" in ab["test_cohort"]["who"]
    assert "NT$" in ab["currency"] and "inputs, not data" in ab["assumptions"]
    assert "862,158" in churn.data_line(ab) and "14 days" in churn.data_line(ab)


def test_skill_files():
    head = (ROOT / "SKILL.md").read_text().split("---")[1]
    assert "name: churn-call-planner" in head and "description:" in head
    cases = [p for p in (ROOT / "evals").iterdir() if p.is_dir()]
    assert len(cases) >= 4 and all((c / "prompt.md").exists() and (c / "case.yaml").exists() and any((c / "graders").glob("*.md")) for c in cases)
    trig = json.loads((ROOT / "trigger-evals.json").read_text())
    assert sum(t["should_trigger"] for t in trig) >= 8 and sum(not t["should_trigger"] for t in trig) >= 8


def test_charts_offline(calls, tmp_path):
    """Line (30 points, best share marked inside the range), diverging bars (one per reason) and ranked bars (one per method)."""
    out = tmp_path / "c.html"
    churn.main(["chart", "profit", "--out", str(out)])
    page = out.read_text()
    assert page.count('class="bar"') == 30 and "best: " in page
    churn.main(["chart", "reasons", "demo-001", "--out", str(out)])
    page = out.read_text()
    assert page.count('class="bar"') == 3 and "17% chance" in page and "Raises risk" in page and "Lowers risk" in page
    churn.main(["chart", "rankers", "--out", str(out)])
    page = out.read_text()
    assert page.count('class="bar"') == 3 and "NT$12.4M" in page and "Learned ranker (LambdaMART)" in page


def test_confidence_levels_floor_and_pilot(calls):
    c = churn.confidence("x", 0.058, 0.25, 15)
    assert c["direction"] == "call more" and c["level"] in {"medium", "high"}
    assert c["floor"]["share"] == min(c["best_share"].values()) and c["pilot"]["churners_needed"] == 289
    assert c["pilot"]["calls"] % 100 == 0 and c["pilot"]["calls"] >= 289 / c["pilot"]["precision_forecast"]
    assert 0 < c["break_even_save_rate"] < 0.25 and c["calibration"]["actual_churn_rate"] > c["calibration"]["expected_churn_rate"]
    low = churn.confidence("x", 0.6, 0.02, 100)                          # tiny save rate, costly calls: no target
    assert low["level"] == "low"


def test_strength_words():
    assert [churn.strength(v) for v in (1.13, 0.715, -0.338, 0.23, -0.2)] == ["strong", "moderate", "moderate", "slight", "slight"]


def test_drivers_bundle_matches_committed_output_and_adds_up():
    bundled = json.loads((ROOT / "references/global_drivers.json").read_text())
    assert bundled == json.loads((ROOT.parents[1] / "data/outputs/p8_global_drivers.json").read_text())
    g = bundled["rule_gap"]
    assert abs(g["rule_reach"] + g["points_from_auto_renew"] + g["points_from_better_order_in_manual"] - g["model_reach"]) < 1e-9
    assert abs(sum(v["share_all"] for v in bundled["themes"].values()) - 1) < 1e-6
    d = churn.drivers()
    assert d["themes"][0]["theme"] == "Payment and plan" and len(d["top_features"]) == 6


def test_drivers_chart_offline(calls, tmp_path):
    out = tmp_path / "d.html"
    churn.main(["chart", "drivers", "--out", str(out)])
    page = out.read_text()
    assert page.count('class="bar"') == 4 and "65.5%" in page and "rule never calls" in page


def test_confidence_page_offline(calls, tmp_path):
    """Dot per view, a pilot slider with its data, and four decision outcomes; no label word printed as the confidence."""
    out = tmp_path / "conf.html"
    churn.main(["chart", "confidence", "--share", "0.058", "--save-rate", "0.25", "--cost", "15", "--out", str(out)])
    page = out.read_text()
    assert page.count('class="bar"') == 3 and 'id="pc"' in page and page.count('class="out"') == 4
    assert "views say calling more" in page and "medium" not in page.lower()
