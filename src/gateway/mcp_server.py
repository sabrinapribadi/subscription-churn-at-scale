"""MCP gateway (ADR-005/006): exposes the shared tool registry to AI agents.

Local (stdio, for desktop AI assistants and IDE agents):
    SERVING_DIR=~/data/kkbox/serving python -m src.gateway.mcp_server
Containers (streamable HTTP, talking to the services):
    MCP_TRANSPORT=streamable-http SCORING_URL=http://scoring:8000 EXPLAIN_URL=http://explain:8000 python -m src.gateway.mcp_server
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import yaml
from mcp.server.mcpserver import MCPServer

from src.genai.tools import build_tools

CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default_config.yaml"
INSTRUCTIONS = ("Churn tools for a subscription retention team. Scores are calibrated probabilities of not renewing within 30 days "
                "after expiry, made 14 days before expiry. Never quote age, gender or city to agents.")


def build_server(client) -> MCPServer:
    srv = MCPServer(name="churn-gateway", instructions=INSTRUCTIONS, version="1")
    for fn in build_tools(client):
        srv.tool(name=fn.__name__, description=inspect.getdoc(fn))(fn)

    @srv.custom_route("/health", methods=["GET"])
    async def health(request):  # same probe as the other services (HTTP transport only)
        from starlette.responses import JSONResponse
        return JSONResponse({"service": "mcp-gateway", "status": "ok", "tools": [f.__name__ for f in build_tools(client)]})

    return srv


def _client():
    if os.environ.get("SCORING_URL"):
        from src.services.clients import HttpClient
        return HttpClient(scoring_url=os.environ["SCORING_URL"], explain_url=os.environ.get("EXPLAIN_URL"))
    from src.genai.explain import Explainer
    from src.genai.providers import get_provider
    from src.services.clients import LocalClient
    from src.services.store import ServingStore
    cfg = yaml.safe_load(CONFIG.read_text())
    return LocalClient(ServingStore(os.path.expanduser(os.environ["SERVING_DIR"])), Explainer(get_provider(cfg["llm"])))


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    kwargs = {"host": "0.0.0.0", "port": int(os.environ.get("PORT", "8000"))} if transport != "stdio" else {}
    build_server(_client()).run(transport, **kwargs)
