"""Catalog API adaptation for MCP tool handlers."""

from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from mcp.server.mcpserver import Context  # noqa: TC002 -- shared with runtime-inspected tool annotations


# Keep the historical logger identity while moving the HTTP boundary out of server.py.
logger = structlog.get_logger("mcp_server.server")


@dataclass
class AppContext:
    """Lifespan state shared by registered tools."""

    client: httpx.AsyncClient
    base_url: str  # nosemgrep: path-traversal — configured by the operator, not a tool argument


def app_context(ctx: Context[AppContext, Any]) -> AppContext:
    """Read the typed lifespan state injected by the MCP SDK."""
    return ctx.request_context.lifespan_context


async def api_get(app: AppContext, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a promoted Catalog API GET route and preserve its JSON/error mapping."""
    url = f"{app.base_url}{path}"
    try:
        response = await app.client.get(url, params=params)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        logger.error("API HTTP error", url=url, status=exc.response.status_code)
        return {"error": f"API returned HTTP {exc.response.status_code}", "url": url}
    except Exception as exc:
        logger.error("API request failed", url=url, error=repr(exc))
        return {"error": f"API request failed: {exc}", "url": url}


async def api_post(app: AppContext, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a promoted Catalog API POST route and preserve its JSON/error mapping."""
    url = f"{app.base_url}{path}"
    try:
        response = await app.client.post(url, json=json_data)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        logger.error("API HTTP error", url=url, status=exc.response.status_code)
        return {"error": f"API returned HTTP {exc.response.status_code}", "url": url}
    except Exception as exc:
        logger.error("API request failed", url=url, error=repr(exc))
        return {"error": f"API request failed: {exc}", "url": url}


async def find_path(app: AppContext, **kwargs: Any) -> dict[str, Any]:
    """Run the shared path policy with Catalog API-backed resolvers."""
    import common.agent_tools as agent_tools  # noqa: PLC0415

    async def resolve_name(_driver: Any, name: str, _entity_type: str) -> dict[str, Any] | None:
        return {"id": name}

    async def find_shortest_path_fn(**params: Any) -> dict[str, Any] | None:
        return await api_get(  # nosemgrep: ssrf — callers validate entity types against a closed set
            app,
            "/api/path",
            {
                "from_name": params.get("from_id", ""),
                "from_type": params.get("from_type", ""),
                "to_name": params.get("to_id", ""),
                "to_type": params.get("to_type", ""),
                "max_depth": params.get("max_depth", 10),
            },
        )

    return await agent_tools.find_path(
        driver=None,
        resolve_name=resolve_name,
        find_shortest_path_fn=find_shortest_path_fn,
        **kwargs,
    )
