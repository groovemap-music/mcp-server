"""MCP server exposing the GrooveMap knowledge graph to AI assistants.

Provides 12 tools for searching, exploring, and analyzing music data:
  search, get_artist_details, get_label_details, get_release_details,
  get_genre_details, get_style_details, find_path, get_trends,
  get_graph_stats, get_collaborators, get_genre_tree, nlq_query

All data is fetched via the GrooveMap Catalog API — no direct database access.

Transports: stdio (default, for Claude Desktop) or streamable-http (hosted).

Configuration via environment variables:
  API_BASE_URL    Base URL for the GrooveMap Catalog API (default: http://localhost:8004)
"""

import sys

# AsyncIterator stays available at runtime because the MCP SDK inspects lifespan
# annotations when registering handlers under Python 3.14. Awaitable/Callable back
# the _ToolHandler runtime type alias below, so they are genuinely used at runtime too.
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from os import getenv
from time import perf_counter
from typing import Any
from urllib.parse import quote as _url_quote

import httpx
import structlog
from common import get_meter, instrument_httpx, setup_telemetry, shutdown_telemetry
from common.agent_tools.discovery import validate_media_filter
from common.media import family_ids
from mcp.server import MCPServer
from mcp.server.mcpserver import Context  # noqa: TC002


logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Telemetry: one meter for the whole package, instruments created once at import.
# ---------------------------------------------------------------------------

_meter = get_meter("groovemap.mcp-server")
_tool_calls = _meter.create_counter(
    "groovemap.mcp.tool.calls",
    description="MCP tool invocations",
)
_tool_duration = _meter.create_histogram(
    "groovemap.mcp.tool.duration",
    unit="s",
    description="MCP tool call duration",
)

_ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


def _instrumented(tool_name: str) -> Callable[[_ToolHandler], _ToolHandler]:
    """Record groovemap.mcp.tool.calls/duration {tool, outcome} around a tool handler.

    outcome is "error" when the handler raises or returns an {"error": ...} dict
    (the shape _api_get/_api_post return on failure instead of raising), "success"
    otherwise. Wraps the plain async function before @mcp.tool() registers it, so
    every call reaching the handler through the MCP protocol is measured.
    """

    def decorator(func: _ToolHandler) -> _ToolHandler:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            start = perf_counter()
            try:
                result = await func(*args, **kwargs)
            except Exception:
                duration = perf_counter() - start
                _tool_calls.add(1, {"tool": tool_name, "outcome": "error"})
                _tool_duration.record(duration, {"tool": tool_name})
                raise
            duration = perf_counter() - start
            outcome = "error" if isinstance(result, dict) and "error" in result else "success"
            _tool_calls.add(1, {"tool": tool_name, "outcome": outcome})
            _tool_duration.record(duration, {"tool": tool_name})
            return result

        return wrapper

    return decorator


_VALID_ENTITY_TYPES = frozenset({"artist", "genre", "label", "style"})
_VALID_SEARCH_TYPES = frozenset({"artist", "label", "master", "release"})
# The ADR 0007 media taxonomy's family ids, computed once at import time. Every family also
# has medium ids beneath it (e.g. vinyl_12 under vinyl); `search`'s media filter accepts both.
_MEDIA_FAMILIES = family_ids()


def _validate_numeric_id(value: str, name: str) -> dict[str, Any] | None:
    """Validate that an ID is numeric. Returns an error dict if invalid, None if OK."""
    if not value.isdigit():
        return {"error": f"Invalid {name}: must be a numeric string (got {value!r})"}
    return None


# ---------------------------------------------------------------------------
# Lifespan: manage HTTP client
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    """Typed lifespan context holding the HTTP client and API base URL."""

    client: httpx.AsyncClient
    base_url: str  # nosemgrep: path-traversal — base_url comes from env var, not user input


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:  # noqa: ARG001
    """Initialize HTTP client on startup, close on shutdown."""
    base_url = getenv("API_BASE_URL", "http://localhost:8004")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # setup_telemetry() runs before app_lifespan (see main()), so instrument_httpx
        # binds to the configured provider. It is a no-op returning False without the
        # 'otel-http' extra or before setup_telemetry has installed a live provider.
        instrument_httpx(client)
        logger.info("🚀 MCP server ready", api_base_url=base_url)
        yield AppContext(client=client, base_url=base_url)
        logger.info("👋 MCP server shut down")


# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helper: extract lifespan context + API call
# ---------------------------------------------------------------------------


def _ctx(ctx: Context[AppContext, Any]) -> AppContext:
    # Context is generic over the lifespan type in v2, so parameterizing it types
    # `lifespan_context` as AppContext instead of dict[str, Any] — no cast, no ignore.
    # Tool signatures use the same parameterized form; the SDK injects on the Context
    # origin, so the type argument is invisible to it and never reaches a tool schema.
    return ctx.request_context.lifespan_context


async def _api_get(app: AppContext, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make a GET request to the GrooveMap Catalog API and return parsed JSON."""
    url = f"{app.base_url}{path}"
    try:
        resp = await app.client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        logger.error("API HTTP error", url=url, status=exc.response.status_code)
        return {"error": f"API returned HTTP {exc.response.status_code}", "url": url}
    except Exception as exc:
        logger.error("API request failed", url=url, error=repr(exc))
        return {"error": f"API request failed: {exc}", "url": url}


async def _api_post(app: AppContext, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make a POST request to the GrooveMap Catalog API and return parsed JSON."""
    url = f"{app.base_url}{path}"
    try:
        resp = await app.client.post(url, json=json_data)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        logger.error("API HTTP error", url=url, status=exc.response.status_code)
        return {"error": f"API returned HTTP {exc.response.status_code}", "url": url}
    except Exception as exc:
        logger.error("API request failed", url=url, error=repr(exc))
        return {"error": f"API request failed: {exc}", "url": url}


async def _call_shared_find_path(app: AppContext, **kwargs: Any) -> dict[str, Any]:
    """Delegate to common.agent_tools.find_path using API-backed resolvers."""
    import common.agent_tools as agent_tools  # noqa: PLC0415

    async def resolve_name(_driver: Any, name: str, _entity_type: str) -> dict[str, Any] | None:
        # The API uses names directly — return the name as the "id" so the path
        # function can forward it to /api/path as from_name / to_name.
        return {"id": name}

    async def find_shortest_path_fn(**params: Any) -> dict[str, Any] | None:
        return await _api_get(  # nosemgrep: ssrf — types validated against _VALID_ENTITY_TYPES allowlist before this call
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


# ---------------------------------------------------------------------------
# Tool 1: search
# ---------------------------------------------------------------------------


async def _search(
    ctx: Context[AppContext, Any],
    query: str,
    types: str = "artist,label,master,release",
    media: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search the music database across artists, labels, masters, and releases.

    Uses full-text search with relevance ranking. Returns matching entities
    with highlights and facet counts (by type, genre, decade).

    Args:
        query: Search terms (minimum 3 characters).
        types: Comma-separated entity types to search (artist, label, master, release).
        media: Optional family or medium ids (ADR 0007 canonical media taxonomy) to narrow
            release results to specific media — for example ["cassette"] would not match
            since "cassette" isn't a taxonomy id, but ["tape"] matches every tape medium and
            ["optical_cd"] matches CD only. Valid families: {families}. Each family also has
            narrower medium ids beneath it (e.g. vinyl_12, optical_cd). An unknown id returns
            an error naming it.
        limit: Maximum results to return (1-100, default 20).
    """
    requested = [t.strip().lower() for t in types.split(",") if t.strip()]
    if not requested:
        requested = list(_VALID_SEARCH_TYPES)
    invalid = [t for t in requested if t not in _VALID_SEARCH_TYPES]
    if invalid:
        return {"error": f"Invalid type(s): {', '.join(invalid)}. Valid: {', '.join(_VALID_SEARCH_TYPES)}"}

    params: dict[str, Any] = {
        "q": query,
        "types": ",".join(requested),
        "limit": min(max(limit, 1), 100),
    }
    if media:
        try:
            params["media"] = validate_media_filter(media)
        except ValueError as exc:
            return {"error": f"{exc} Valid families: {', '.join(_MEDIA_FAMILIES)}."}

    app = _ctx(ctx)
    return await _api_get(app, "/api/search", params)


# The `Valid families: {families}` placeholder above is filled in from `_MEDIA_FAMILIES`
# here, before the tool is registered, so the MCP schema description the client sees — and
# `search.__doc__` for anyone reading the source — both come from the one taxonomy call
# instead of a hand-copied list that can drift from it. Decorators are applied by hand
# (rather than as `@mcp.tool()` / `@_instrumented("search")` above the def) because the
# docstring has to be formatted first; `name="search"` restores the registered tool name
# that `_search`'s own `__name__` would otherwise give it.
_search.__doc__ = (_search.__doc__ or "").format(families=", ".join(_MEDIA_FAMILIES))
search = mcp.tool(name="search")(_instrumented("search")(_search))


# ---------------------------------------------------------------------------
# Tools 2-6: entity details
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("get_artist_details")
async def get_artist_details(
    ctx: Context[AppContext, Any],
    artist_id: str,
) -> dict[str, Any]:
    """Get detailed information about an artist.

    Returns the artist's name, genres, styles, release count, and group memberships.
    Use 'search' first to find the artist's ID.

    Args:
        artist_id: The Discogs artist ID (numeric string).
    """
    app = _ctx(ctx)
    if err := _validate_numeric_id(artist_id, "artist_id"):
        return err
    return await _api_get(app, f"/api/node/{artist_id}", {"type": "artist"})


@mcp.tool()
@_instrumented("get_label_details")
async def get_label_details(
    ctx: Context[AppContext, Any],
    label_id: str,
) -> dict[str, Any]:
    """Get detailed information about a record label.

    Returns the label's name and total release count.
    Use 'search' first to find the label's ID.

    Args:
        label_id: The Discogs label ID (numeric string).
    """
    app = _ctx(ctx)
    if err := _validate_numeric_id(label_id, "label_id"):
        return err
    return await _api_get(app, f"/api/node/{label_id}", {"type": "label"})


@mcp.tool()
@_instrumented("get_release_details")
async def get_release_details(
    ctx: Context[AppContext, Any],
    release_id: str,
) -> dict[str, Any]:
    """Get detailed information about a release (album, single, etc.).

    Returns the title, year, artists, labels, genres, and styles. When the release has media
    data, the response also carries a top-level `media` block — the ADR 0007 canonical media
    taxonomy's shape, additive to the fields above:
      - `families`: sorted family ids the release's media belong to (e.g. ["vinyl"]).
      - `items`: one entry per physical or digital medium, each with `family`, `medium`
        (e.g. "vinyl_12"), `qty`, and attributes such as `size_inches`, `speed_rpm`,
        `channels`, `codec`, `variants`, and `appearance`.
      - `release_kind`: "album", "single", "ep", "broadcast", "other", or null.
      - `edition`: edition facts such as "reissue", "remastered", "limited", "promo".
      - `unmapped`: raw provider values the taxonomy did not recognize, kept for coverage.
    Use the `media` filter on 'search' to find cassette-only or CD-only releases before
    calling this tool. Use 'search' first to find the release's ID.

    Args:
        release_id: The Discogs release ID (numeric string).
    """
    app = _ctx(ctx)
    if err := _validate_numeric_id(release_id, "release_id"):
        return err
    return await _api_get(app, f"/api/node/{release_id}", {"type": "release"})


@mcp.tool()
@_instrumented("get_genre_details")
async def get_genre_details(
    ctx: Context[AppContext, Any],
    genre_name: str,
) -> dict[str, Any]:
    """Get detailed information about a music genre.

    Returns the genre name and the number of artists associated with it.

    Args:
        genre_name: Exact genre name (e.g. "Jazz", "Electronic", "Rock").
    """
    app = _ctx(ctx)
    return await _api_get(app, f"/api/node/{_url_quote(genre_name, safe='')}", {"type": "genre"})


@mcp.tool()
@_instrumented("get_style_details")
async def get_style_details(
    ctx: Context[AppContext, Any],
    style_name: str,
) -> dict[str, Any]:
    """Get detailed information about a music style (sub-genre).

    Returns the style name and the number of artists associated with it.

    Args:
        style_name: Exact style name (e.g. "Acid Jazz", "Ambient", "Punk").
    """
    app = _ctx(ctx)
    return await _api_get(app, f"/api/node/{_url_quote(style_name, safe='')}", {"type": "style"})


# ---------------------------------------------------------------------------
# Tool 7: find_path
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("find_path")
async def find_path(
    ctx: Context[AppContext, Any],
    from_name: str,
    from_type: str,
    to_name: str,
    to_type: str,
    max_depth: int = 10,
) -> dict[str, Any]:
    """Find the shortest path between two entities in the knowledge graph.

    Discovers how two artists, labels, genres, or styles are connected
    through releases and relationships.

    Args:
        from_name: Name of the starting entity.
        from_type: Type of starting entity (artist, genre, label, style).
        to_name: Name of the destination entity.
        to_type: Type of destination entity (artist, genre, label, style).
        max_depth: Maximum path length to search (1-10, default 10).
    """
    from_type_lower = from_type.lower()
    to_type_lower = to_type.lower()

    if from_type_lower not in _VALID_ENTITY_TYPES:
        return {"error": f"Invalid from_type: {from_type}. Must be one of: {', '.join(sorted(_VALID_ENTITY_TYPES))}"}
    if to_type_lower not in _VALID_ENTITY_TYPES:
        return {"error": f"Invalid to_type: {to_type}. Must be one of: {', '.join(sorted(_VALID_ENTITY_TYPES))}"}

    app = _ctx(ctx)
    return await _call_shared_find_path(
        app,
        from_name=from_name,
        from_type=from_type_lower,
        to_name=to_name,
        to_type=to_type_lower,
        # Clamp to the API's real ceiling (api/routers/explore.py:_MAX_PATH_DEPTH=10) —
        # advertising a wider range here just makes 11-15 always fail with HTTP 422.
        max_depth=min(max(int(max_depth) if str(max_depth).lstrip("-").isdigit() else 10, 1), 10),
    )


# ---------------------------------------------------------------------------
# Tool 8: get_trends
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("get_trends")
async def get_trends(
    ctx: Context[AppContext, Any],
    name: str,
    entity_type: str = "artist",
) -> dict[str, Any]:
    """Get the release timeline for an entity (releases per year).

    Useful for understanding an artist's, label's, or genre's activity over time.

    Args:
        name: Exact name of the entity.
        entity_type: Type of entity (artist, genre, label, style).
    """
    entity_type_lower = entity_type.lower()
    if entity_type_lower not in _VALID_ENTITY_TYPES:
        return {"error": f"Invalid type: {entity_type}. Must be artist, genre, label, or style"}

    app = _ctx(ctx)
    return await _api_get(
        app,
        "/api/trends",
        {
            "name": name,
            "type": entity_type_lower,
        },
    )


# ---------------------------------------------------------------------------
# Tool 9: get_graph_stats
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("get_graph_stats")
async def get_graph_stats(
    ctx: Context[AppContext, Any],
) -> dict[str, Any]:
    """Get an overview of the knowledge graph — total counts for each entity type.

    Returns counts for artists, labels, releases, masters, genres, and styles.
    Useful for understanding the size and scope of the database.
    """
    app = _ctx(ctx)
    return await _api_get(app, "/api/graph/stats")


# ---------------------------------------------------------------------------
# Tool 10: get_collaborators
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("get_collaborators")
async def get_collaborators(
    ctx: Context[AppContext, Any],
    artist_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Find artists who collaborate with a given artist through shared releases.

    Returns collaborators ranked by number of shared releases, with temporal
    data showing when collaborations occurred.

    Args:
        artist_id: The Discogs artist ID (numeric string). Use 'search' to find it.
        limit: Maximum collaborators to return (1-100, default 20).
    """
    app = _ctx(ctx)
    if err := _validate_numeric_id(artist_id, "artist_id"):
        return err
    return await _api_get(
        app,
        f"/api/collaborators/{artist_id}",
        {"limit": min(max(limit, 1), 100)},
    )


# ---------------------------------------------------------------------------
# Tool 11: get_genre_tree
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("get_genre_tree")
async def get_genre_tree(
    ctx: Context[AppContext, Any],
) -> dict[str, Any]:
    """Get the full genre/style hierarchy from the knowledge graph.

    Returns all genres with their nested styles and release counts,
    derived from release co-occurrence. Useful for understanding the
    taxonomy of music in the database.
    """
    app = _ctx(ctx)
    return await _api_get(app, "/api/genre-tree")


# ---------------------------------------------------------------------------
# Tool 12: nlq_query
# ---------------------------------------------------------------------------


@mcp.tool()
@_instrumented("nlq_query")
async def nlq_query(
    ctx: Context[AppContext, Any],
    query: str,
) -> dict[str, Any]:
    """Ask a natural language question about the music knowledge graph.

    The system interprets your question, queries the graph using appropriate
    tools, and returns a natural language answer with referenced entities.
    Use this for complex questions that span multiple entities or relationships.

    Examples:
    - "Find artists who recorded for both Factory Records and Rough Trade"
    - "What's the most prolific electronic music label?"
    - "How are Kraftwerk and Afrika Bambaataa connected?"
    """
    app = _ctx(ctx)
    return await _api_post(app, "/api/nlq/query", json_data={"query": query})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


_VALID_TRANSPORTS = {"stdio", "streamable-http"}


def main() -> None:
    """Run the MCP server. Use --transport to select transport (default: stdio)."""
    transport = "stdio"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--transport", "-t") and i < len(sys.argv) - 1:
            transport = sys.argv[i + 1]
            break
        if arg.startswith("--transport="):
            transport = arg.split("=", 1)[1]
            break

    if transport not in _VALID_TRANSPORTS:
        transport = "stdio"

    # setup_telemetry never fails startup: with OTEL_EXPORTER_OTLP_ENDPOINT unset it
    # installs a no-op MeterProvider and the service behaves exactly as before. The
    # try/finally ensures shutdown_telemetry flushes even a short stdio session, whose
    # process would otherwise exit before the periodic exporter's next push.
    setup_telemetry("mcp-server")
    try:
        # v2 overloads `run` per transport, each with its own keyword set, so a `str`
        # matches no variant. Branch on the validated value instead of casting — this
        # keeps the call type-checked rather than silencing it.
        if transport == "streamable-http":
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="stdio")
    finally:
        shutdown_telemetry()


if __name__ == "__main__":
    main()
