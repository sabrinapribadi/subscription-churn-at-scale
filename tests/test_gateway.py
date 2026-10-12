"""MCP gateway over the real protocol, using the SDK's in-memory client (ADR-005/006)."""

import asyncio
import json

from mcp.client import Client

from src.gateway.mcp_server import build_server


def run(coro):
    return asyncio.run(coro)


def test_mcp_lists_the_four_tools_with_schemas(client):
    async def go():
        async with Client(build_server(client)) as c:
            return (await c.list_tools()).tools
    tools = {t.name: t for t in run(go())}
    assert set(tools) == {"member_risk", "why_at_risk", "call_list", "what_if"}
    assert tools["member_risk"].input_schema["required"] == ["member_id"]


def test_mcp_tools_answer_with_grounded_data(client, store):
    m = store.order[0]
    async def go():
        async with Client(build_server(client)) as c:
            out = {}
            for name, args in (("member_risk", {"member_id": m}), ("why_at_risk", {"member_id": m}),
                               ("call_list", {"share": 0.1, "limit": 3}), ("what_if", {"save_rate": 0.3, "cost_per_call": 0})):
                r = await c.call_tool(name, args)
                assert not r.is_error, (name, r)
                out[name] = json.loads(r.content[0].text)
            return out
    o = run(go())
    assert o["member_risk"]["priority_rank"] == 1
    assert o["why_at_risk"]["grounded"] and o["why_at_risk"]["note"].endswith(f"Suggested action: {o['why_at_risk']['suggested_action']}.")
    assert all(r["feature"] not in {"gender", "age", "city"} for r in o["why_at_risk"]["reasons"])
    assert len(o["call_list"]["members"]) == 3 and o["what_if"]["save_rate"] == 0.3


def test_mcp_unknown_member_is_an_error_not_a_crash(client):
    async def go():
        async with Client(build_server(client)) as c:
            return await c.call_tool("member_risk", {"member_id": "nobody"})
    assert run(go()).is_error
