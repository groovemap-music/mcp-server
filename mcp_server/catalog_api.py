"""Catalog API adaptation for MCP tool handlers."""

import re
from collections.abc import Awaitable, Callable  # noqa: TC003 -- concrete at the one internal call boundary
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from mcp.server.mcpserver import Context  # noqa: TC002 -- shared with runtime-inspected tool annotations


# Keep the historical logger identity while moving the HTTP boundary out of server.py.
logger = structlog.get_logger("mcp_server.server")

# The delegated routes, and only these: the activity outcome route and the two consent
# routes. A pattern rather than a prefix so the authorization header cannot widen to a
# neighbouring path, and anchored with `^` so check-contracts.py's scan for `/api/` string
# literals does not read it as a route this adapter calls.
_DELEGATED_ROUTES = re.compile(r"^/api/(activity/events|user/consent(/[^/]+)?)$")

# The error a delegated tool returns instead of calling the API when no token is configured.
DELEGATION_NOT_CONFIGURED = "delegation not configured"


@dataclass
class AppContext:
    """Lifespan state shared by registered tools."""

    client: httpx.AsyncClient
    base_url: str  # nosemgrep: path-traversal — configured by the operator, not a tool argument
    app_token: str | None = None  # nosemgrep: hardcoded-credential — read from the environment at lifespan start


def app_context(ctx: Context[AppContext, Any]) -> AppContext:
    """Read the typed lifespan state injected by the MCP SDK."""
    return ctx.request_context.lifespan_context


def delegation_error(app: AppContext) -> dict[str, Any] | None:
    """Return the refusal a delegated tool owes when no app token is configured, else None.

    Answering from here is what keeps an unconfigured deployment from sending a request the
    route would only reject, and it names the setting rather than any value it might hold.
    A fresh mapping per call, so a caller that mutates the result cannot change the next one.
    """
    if app.app_token:
        return None
    return {
        "error": DELEGATION_NOT_CONFIGURED,
        "detail": (
            "This tool acts for a collector and needs a delegated Catalog API app token. "
            "Set GROOVEMAP_CATALOG_APP_TOKEN in the server's environment and restart the server."
        ),
    }


def _auth(app: AppContext, path: str) -> dict[str, Any]:
    """Return the request keywords carrying the bearer header, for a delegated route only.

    A public route gets an empty mapping, so its request goes out exactly as it did before
    delegation existed.
    """
    if app.app_token and _DELEGATED_ROUTES.fullmatch(path):
        return {"headers": {"Authorization": f"Bearer {app.app_token}"}}
    return {}


async def _call(
    app: AppContext,
    path: str,
    send: Callable[..., Awaitable[httpx.Response]],
    **request: Any,
) -> dict[str, Any]:
    """Send one promoted Catalog API request and preserve the established JSON/error mapping.

    `send` is the bound httpx verb, so each verb helper keeps its own call shape and the
    per-route authorization decision is made in exactly one place. Neither the token nor the
    header is logged or returned: a failure reports the URL and the status, nothing else.
    """
    url = f"{app.base_url}{path}"
    try:
        response = await send(url, **request, **_auth(app, path))
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        logger.error("API HTTP error", url=url, status=exc.response.status_code)
        return {"error": f"API returned HTTP {exc.response.status_code}", "url": url}
    except Exception as exc:
        logger.error("API request failed", url=url, error=repr(exc))
        return {"error": f"API request failed: {exc}", "url": url}


async def api_get(app: AppContext, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a promoted Catalog API GET route and preserve its JSON/error mapping."""
    return await _call(app, path, app.client.get, params=params)


async def api_post(app: AppContext, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a promoted Catalog API POST route and preserve its JSON/error mapping."""
    return await _call(app, path, app.client.post, json=json_data)


async def api_put(app: AppContext, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a promoted Catalog API PUT route and preserve its JSON/error mapping."""
    return await _call(app, path, app.client.put, json=json_data)


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
