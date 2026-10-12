"""Contract tests for feature-svc, scoring-svc and explain-svc (ADR-005)."""

import pytest
from fastapi.testclient import TestClient

from src.genai.explain import Explainer
from src.services.apps import explain_app, feature_app, scoring_app
from src.services.contracts import CallList, Explanation, MemberFeatures, Reasons, Score, WhatIf


@pytest.fixture(scope="module")
def apps(store):
    from src.services.clients import LocalClient
    return (TestClient(feature_app(store)), TestClient(scoring_app(store)),
            TestClient(explain_app(LocalClient(store, Explainer()), Explainer())))


def test_health_reports_model_version(apps, store):
    for app in apps[:2]:
        h = app.get("/health").json()
        assert h["status"] == "ok" and h["model_version"] == store.model_version and h["members"] == len(store.df)
    assert apps[2].get("/health").json()["provider"] == "template"


def test_feature_contract(apps, store):
    m = store.order[0]
    body = apps[0].get(f"/members/{m}/features").json()
    f = MemberFeatures(**body)
    assert set(f.features) == set(store.features) and f.snapshot_date < f.expiry_date


def test_score_contract_and_ranges(apps, store):
    s = Score(**apps[1].get(f"/members/{store.order[0]}/score").json())
    assert 0 <= s.churn_probability <= 1 and s.priority_rank == 1 and s.priority_percentile == 100
    assert s.expected_value_at_risk == pytest.approx(s.churn_probability * s.member_value)


def test_reasons_contract_and_sensitive_flag(apps, store):
    rs = Reasons(**apps[1].get(f"/members/{store.order[0]}/reasons?k=8").json())
    assert len(rs.reasons) == 8
    assert all(r.shown_to_agent == (r.feature not in {"gender", "age", "city"}) for r in rs.reasons)
    assert [abs(r.contribution) for r in rs.reasons] == sorted((abs(r.contribution) for r in rs.reasons), reverse=True)


def test_call_list_is_ordered_by_expected_value(apps):
    cl = CallList(**apps[1].post("/call-list", json={"share": 0.1, "limit": 50}).json())
    ev = [m.expected_value_at_risk for m in cl.members]
    assert ev == sorted(ev, reverse=True) and cl.summary.members_called == 250
    assert [m.priority_rank for m in cl.members] == list(range(1, 51))


def test_call_list_rejects_bad_input(apps):
    assert apps[1].post("/call-list", json={"share": 0}).status_code == 422
    assert apps[1].post("/call-list", json={"share": 0.1, "limit": 10_000}).status_code == 422


def test_what_if_contract(apps):
    w = WhatIf(**apps[1].get("/what-if?save_rate=0.2&cost_per_call=20").json())
    assert 0 < w.best_share <= 0.5 and set(w.profit_at_10pct) == {"probability", "expected_value", "lambdamart"}


def test_unknown_member_is_404_everywhere(apps):
    assert apps[0].get("/members/nobody/features").status_code == 404
    assert apps[1].get("/members/nobody/score").status_code == 404
    assert apps[1].get("/members/nobody/reasons").status_code == 404
    assert apps[2].get("/members/nobody/explanation").status_code == 404


def test_explanation_contract(apps, store):
    e = Explanation(**apps[2].get(f"/members/{store.order[0]}/explanation").json())
    assert e.grounded and not e.grounded_fallback and e.prompt_version == "explain_member.v1"
    assert e.narrative.endswith(f"Suggested action: {e.suggested_action}.") and e.meter.cost_usd == 0
