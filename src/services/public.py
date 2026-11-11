"""Public, read-only demo of the churn tools: REST plus a stateless MCP endpoint at /mcp (ADR-010; rules R19, R20).

    SNAPSHOT=deploy/public_snapshot.json uvicorn src.services.public:app --port 8000

- No model libraries, no real member rows, no API key: everything comes from a checksummed snapshot.
- Call-list totals are the real cohort's; member lookups are synthetic demo members ("demo-001" … "demo-100").
- Inputs that are not identifiers are refused and never echoed (prompt-injection defence).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from mcp.server.transport_security import TransportSecuritySettings

from src.gateway.mcp_server import build_server
from src.services.contracts import (
    CallList,
    CallListRequest,
    CallListSummary,
    Explanation,
    Score,
    WhatIf,
)
from src.services.scenarios import what_if_from

ROOT = Path(__file__).resolve().parents[2]
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
MEMBERS_NOTE = "Real member rows are not published (competition data terms); see the demo members demo-001 to demo-100."


def shown(x: str) -> str:
    return f"'{x}'" if SAFE_ID.fullmatch(str(x)) else "the given input (not a member id)"


class PublicClient:
    """Same interface as LocalClient, answered from the snapshot."""

    def __init__(self, snap: dict):
        self.snap, self.grid = snap, snap["call_grid"]

    def _demo(self, member_id: str) -> dict:
        d = self.snap["demo"].get(member_id) if isinstance(member_id, str) and len(member_id) <= 40 else None
        if d is None:
            raise KeyError(f"No demo member {shown(member_id)}. {MEMBERS_NOTE}")
        return d

    def score(self, member_id: str) -> Score:
        return Score(**self._demo(member_id)["score"])

    def explanation(self, member_id: str) -> Explanation:
        return Explanation(**self._demo(member_id)["explanation"])

    def call_list(self, **req) -> CallList:
        r = CallListRequest(**req)
        i = min(len(self.grid["k"]), max(1, round(r.share * len(self.grid["k"])))) - 1        # nearest 0.1%
        r = r.model_copy(update={"share": (i + 1) / len(self.grid["k"])})
        k, ev = self.grid["k"][i], self.grid["expected_value_at_risk"][i]
        s = CallListSummary(members_called=k, expected_churners=self.grid["expected_churners"][i], expected_value_at_risk=ev,
                            expected_profit=round(r.save_rate * ev - r.cost_per_call * k, 0))
        return PublicCallList(request=r, summary=s, members=[])

    def what_if(self, save_rate: float, cost_per_call: float) -> WhatIf:
        return what_if_from(self.snap["scenarios"], save_rate, cost_per_call)


class PublicCallList(CallList):
    members_note: str = MEMBERS_NOTE


def load_snapshot() -> dict:
    p = Path(os.environ.get("SNAPSHOT", ROOT / "deploy" / "public_snapshot.json"))
    return json.loads(p.read_text())


def allowed_hosts() -> list[str]:
    """DNS-rebinding protection on: localhost plus the hostnames the platform sets, plus PUBLIC_HOSTS (comma-separated)."""
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    hosts += [os.environ[v] for v in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL") if os.environ.get(v)]
    return hosts + [h.strip() for h in os.environ.get("PUBLIC_HOSTS", "").split(",") if h.strip()]


SNAP = load_snapshot()
CLIENT = PublicClient(SNAP)
_hosts = allowed_hosts()
MCP = build_server(CLIENT).streamable_http_app(
    stateless_http=True, json_response=True, streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=_hosts,
                                                 allowed_origins=[f"{s}://{h}" for h in _hosts for s in ("http", "https")]))


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    async with MCP.router.lifespan_context(MCP):
        yield


app = FastAPI(title="Subscription Churn API (public demo)", version="1", lifespan=lifespan,
              description="Calibrated churn risk and call-list economics from a model trained on a public music-subscription "
                          "dataset. Totals are the real cohort's; member lookups are synthetic demo members. Read-only; notes "
                          "are precomputed. MCP endpoint: /mcp.")
app.mount("/mcp", MCP)


def _member(fn, member_id: str):
    try:
        return fn(member_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from None


@app.get("/")
def root() -> dict:
    return {"name": "subscription-churn-at-scale", "docs": "/docs", "mcp": "/mcp", "model_version": SNAP["model_version"],
            "cohort_members": SNAP["call_grid"]["members"], "demo_members": sorted(SNAP["demo"])[:3] + ["…"],
            "data_terms": SNAP["data_terms"], "results_page": "https://sabrinapribadi.github.io/subscription-churn-at-scale/"}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model_version": SNAP["model_version"], "notes": "precomputed (no LLM calls on this host)"}


@app.get("/members/{member_id}/score", response_model=Score)
def score(member_id: str):
    return _member(CLIENT.score, member_id)


@app.get("/members/{member_id}/explanation", response_model=Explanation)
def explanation(member_id: str):
    return _member(CLIENT.explanation, member_id)


@app.get("/call-list", response_model=PublicCallList)
def call_list(share: float = Query(0.10, gt=0, le=1), save_rate: float = Query(0.20, ge=0, le=1), cost_per_call: float = Query(20.0, ge=0)):
    return CLIENT.call_list(share=share, save_rate=save_rate, cost_per_call=cost_per_call)


@app.get("/what-if", response_model=WhatIf)
def what_if(save_rate: float = Query(0.2, ge=0, le=1), cost_per_call: float = Query(20.0, ge=0)):
    return CLIENT.what_if(save_rate, cost_per_call)
