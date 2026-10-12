"""Two clients with one interface (ADR-005): in-process for tests and laptops, HTTP for containers."""

from __future__ import annotations

import httpx

from src.services.contracts import CallList, CallListRequest, Explanation, MemberFeatures, Reasons, Score, WhatIf


class LocalClient:
    def __init__(self, store, explainer):
        self.store, self.explainer = store, explainer

    def features(self, member_id: str) -> MemberFeatures:
        return self.store.member_features(member_id)

    def score(self, member_id: str) -> Score:
        return self.store.score(member_id)

    def reasons(self, member_id: str, k: int = 5) -> Reasons:
        return self.store.reasons(member_id, k)

    def call_list(self, **req) -> CallList:
        return self.store.call_list(CallListRequest(**req))

    def explanation(self, member_id: str) -> Explanation:
        s = self.score(member_id)
        return self.explainer.cached(s) or self.explainer.explain(s, self.reasons(member_id))

    def what_if(self, save_rate: float, cost_per_call: float) -> WhatIf:
        return self.store.what_if(save_rate, cost_per_call)


class HttpClient:
    def __init__(self, scoring_url: str, explain_url: str | None = None, feature_url: str | None = None, timeout: float = 10.0):
        self.s, self.e, self.f = scoring_url.rstrip("/"), (explain_url or "").rstrip("/"), (feature_url or "").rstrip("/")
        self.http = httpx.Client(timeout=timeout)

    def _get(self, url):
        r = self.http.get(url)
        if r.status_code == 404:
            raise KeyError(url.rsplit("/", 2)[-2])
        r.raise_for_status()
        return r.json()

    def features(self, member_id: str) -> MemberFeatures:
        return MemberFeatures(**self._get(f"{self.f}/members/{member_id}/features"))

    def score(self, member_id: str) -> Score:
        return Score(**self._get(f"{self.s}/members/{member_id}/score"))

    def reasons(self, member_id: str, k: int = 5) -> Reasons:
        return Reasons(**self._get(f"{self.s}/members/{member_id}/reasons?k={k}"))

    def call_list(self, **req) -> CallList:
        r = self.http.post(f"{self.s}/call-list", json=CallListRequest(**req).model_dump()); r.raise_for_status()
        return CallList(**r.json())

    def explanation(self, member_id: str) -> Explanation:
        return Explanation(**self._get(f"{self.e}/members/{member_id}/explanation"))

    def what_if(self, save_rate: float, cost_per_call: float) -> WhatIf:
        return WhatIf(**self._get(f"{self.s}/what-if?save_rate={save_rate}&cost_per_call={cost_per_call}"))
