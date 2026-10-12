"""FastAPI apps for feature-svc, scoring-svc and explain-svc (ADR-005). One image; SERVICE picks the app.

    SERVICE=scoring SERVING_DIR=~/data/kkbox/serving uvicorn src.services.apps:app --port 8002
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query

from src.genai.explain import Explainer
from src.genai.providers import get_provider
from src.services.clients import HttpClient
from src.services.contracts import CallList, CallListRequest, Explanation, Health, MemberFeatures, Reasons, Score, WhatIf
from src.services.store import ServingStore

CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default_config.yaml"


def _404(member_id: str):
    raise HTTPException(status_code=404, detail=f"unknown member {member_id}")


def feature_app(store: ServingStore) -> FastAPI:
    app = FastAPI(title="feature-svc", version=store.model_version)

    @app.get("/health", response_model=Health)
    def health():
        return Health(service="feature-svc", model_version=store.model_version, members=len(store.df))

    @app.get("/members/{member_id}/features", response_model=MemberFeatures)
    def features(member_id: str):
        try:
            return store.member_features(member_id)
        except KeyError:
            _404(member_id)

    return app


def scoring_app(store: ServingStore) -> FastAPI:
    app = FastAPI(title="scoring-svc", version=store.model_version)

    @app.get("/health", response_model=Health)
    def health():
        return Health(service="scoring-svc", model_version=store.model_version, members=len(store.df))

    @app.get("/members/{member_id}/score", response_model=Score)
    def score(member_id: str):
        try:
            return store.score(member_id)
        except KeyError:
            _404(member_id)

    @app.get("/members/{member_id}/reasons", response_model=Reasons)
    def reasons(member_id: str, k: int = Query(5, ge=1, le=15)):
        try:
            return store.reasons(member_id, k)
        except KeyError:
            _404(member_id)

    @app.post("/call-list", response_model=CallList)
    def call_list(req: CallListRequest):
        return store.call_list(req)

    @app.get("/what-if", response_model=WhatIf)
    def what_if(save_rate: float = Query(0.2, ge=0, le=1), cost_per_call: float = Query(20.0, ge=0)):
        try:
            return store.what_if(save_rate, cost_per_call)
        except KeyError:
            raise HTTPException(status_code=503, detail="scenario curves not loaded")

    return app


def explain_app(client, explainer: Explainer) -> FastAPI:
    """client: any object with score() and reasons() (LocalClient in tests, HttpClient to scoring-svc in containers)."""
    app = FastAPI(title="explain-svc", version="1")

    @app.get("/health")
    def health():
        return {"service": "explain-svc", "status": "ok", "provider": explainer.provider.name, "model": explainer.provider.model,
                "prompt": f"{explainer.prompt.name}.{explainer.prompt.version}", "cached": len(explainer.cache)}

    @app.get("/members/{member_id}/explanation", response_model=Explanation)
    def explanation(member_id: str):
        try:
            s = client.score(member_id)
            return explainer.cached(s) or explainer.explain(s, client.reasons(member_id))
        except KeyError:
            _404(member_id)

    return app


def _build():
    service = os.environ.get("SERVICE", "scoring")
    cfg = yaml.safe_load(CONFIG.read_text())
    if service == "explain":
        client = HttpClient(scoring_url=os.environ["SCORING_URL"])
        return explain_app(client, Explainer(get_provider(cfg["llm"])))
    store = ServingStore(os.path.expanduser(os.environ["SERVING_DIR"]))
    return feature_app(store) if service == "features" else scoring_app(store)


app = _build() if os.environ.get("SERVICE") else None
