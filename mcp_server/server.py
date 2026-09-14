"""Compose the GrooveMap MCP server, its runtime resources, and transport."""

import sys
from collections.abc import AsyncIterator  # noqa: TC003 -- inspected by the MCP SDK
from contextlib import asynccontextmanager
from os import getenv

import httpx
import structlog
from common import instrument_httpx, setup_telemetry, shutdown_telemetry, start_event_loop_monitor
from mcp.server import MCPServer

from mcp_server.catalog_api import AppContext
from mcp_server.registration import register_tools
from mcp_server.transport import run_transport, select_transport


__all__ = [
    "AppContext",
    "app_lifespan",
    "find_path",
    "get_artist_details",
    "get_collaborators",
    "get_genre_details",
    "get_genre_tree",
    "get_graph_stats",
    "get_label_details",
    "get_release_details",
    "get_style_details",
    "get_trends",
    "main",
    "mcp",
    "nlq_query",
    "search",
]

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:  # noqa: ARG001
    """Create and instrument the concrete Catalog API client for one server run.

    The delegated app token is read here and only here. Reading it once at startup is what
    makes it a deployment setting rather than something an agent can supply: no tool takes
    it as an argument, and a tool cannot reach the environment through the lifespan state.
    Its presence is logged; its value never is.
    """
    base_url = getenv("API_BASE_URL", "http://localhost:8004")
    app_token = getenv("GROOVEMAP_CATALOG_APP_TOKEN") or None
    async with httpx.AsyncClient(timeout=30.0) as client:
        instrument_httpx(client)
        start_event_loop_monitor()
        logger.info("🚀 MCP server ready", api_base_url=base_url, delegation_configured=app_token is not None)
        yield AppContext(client=client, base_url=base_url, app_token=app_token)
        logger.info("👋 MCP server shut down")


mcp = MCPServer(
    "GrooveMap",
    lifespan=app_lifespan,
    instructions=(
        "Music knowledge graph server. Use 'search' to find entities, "
        "'get_*_details' for deep info, 'find_path' for connections, "
        "'get_trends' for timelines, 'get_graph_stats' for an overview, "
        "'get_collaborators' for artist collaboration networks, and "
        "'get_genre_tree' for the full genre/style hierarchy."
    ),
)

(
    search,
    get_artist_details,
    get_label_details,
    get_release_details,
    get_genre_details,
    get_style_details,
    find_path,
    get_trends,
    get_graph_stats,
    get_collaborators,
    get_genre_tree,
    nlq_query,
) = register_tools(mcp)


def main() -> None:
    """Run the configured MCP transport, with telemetry bracketing its lifecycle."""
    transport = select_transport(sys.argv[1:])
    setup_telemetry("mcp-server")
    try:
        run_transport(mcp, transport)
    finally:
        shutdown_telemetry()


if __name__ == "__main__":
    main()
