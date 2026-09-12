"""Argument policy and Catalog API routing for GrooveMap MCP tools."""

from typing import Any
from urllib.parse import quote as url_quote

from common.agent_tools.discovery import validate_media_filter
from common.media import family_ids
from mcp.server.mcpserver import Context  # noqa: TC002 -- identifies injected context to the MCP SDK

from mcp_server.catalog_api import AppContext, api_get, api_post, app_context
from mcp_server.catalog_api import find_path as api_find_path


_VALID_ENTITY_TYPES = frozenset({"artist", "genre", "label", "style"})
_VALID_SEARCH_TYPES = frozenset({"artist", "label", "master", "release"})
_MEDIA_FAMILIES = family_ids()


def _validate_numeric_id(value: str, name: str) -> dict[str, Any] | None:
    """Return the established MCP error shape when an entity ID is not numeric."""
    if not value.isdigit():
        return {"error": f"Invalid {name}: must be a numeric string (got {value!r})"}
    return None


async def search(
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
    requested = [entity_type.strip().lower() for entity_type in types.split(",") if entity_type.strip()]
    if not requested:
        requested = list(_VALID_SEARCH_TYPES)
    invalid = [entity_type for entity_type in requested if entity_type not in _VALID_SEARCH_TYPES]
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

    return await api_get(app_context(ctx), "/api/search", params)


search.__doc__ = (search.__doc__ or "").format(families=", ".join(_MEDIA_FAMILIES))


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
    if error := _validate_numeric_id(artist_id, "artist_id"):
        return error
    return await api_get(app_context(ctx), f"/api/node/{artist_id}", {"type": "artist"})


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
    if error := _validate_numeric_id(label_id, "label_id"):
        return error
    return await api_get(app_context(ctx), f"/api/node/{label_id}", {"type": "label"})


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
    if error := _validate_numeric_id(release_id, "release_id"):
        return error
    return await api_get(app_context(ctx), f"/api/node/{release_id}", {"type": "release"})


async def get_genre_details(
    ctx: Context[AppContext, Any],
    genre_name: str,
) -> dict[str, Any]:
    """Get detailed information about a music genre.

    Returns the genre name and the number of artists associated with it.

    Args:
        genre_name: Exact genre name (e.g. "Jazz", "Electronic", "Rock").
    """
    return await api_get(app_context(ctx), f"/api/node/{url_quote(genre_name, safe='')}", {"type": "genre"})


async def get_style_details(
    ctx: Context[AppContext, Any],
    style_name: str,
) -> dict[str, Any]:
    """Get detailed information about a music style (sub-genre).

    Returns the style name and the number of artists associated with it.

    Args:
        style_name: Exact style name (e.g. "Acid Jazz", "Ambient", "Punk").
    """
    return await api_get(app_context(ctx), f"/api/node/{url_quote(style_name, safe='')}", {"type": "style"})


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

    return await api_find_path(
        app_context(ctx),
        from_name=from_name,
        from_type=from_type_lower,
        to_name=to_name,
        to_type=to_type_lower,
        max_depth=min(max(int(max_depth) if str(max_depth).lstrip("-").isdigit() else 10, 1), 10),
    )


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
    return await api_get(app_context(ctx), "/api/trends", {"name": name, "type": entity_type_lower})


async def get_graph_stats(ctx: Context[AppContext, Any]) -> dict[str, Any]:
    """Get an overview of the knowledge graph — total counts for each entity type.

    Returns counts for artists, labels, releases, masters, genres, and styles.
    Useful for understanding the size and scope of the database.
    """
    return await api_get(app_context(ctx), "/api/graph/stats")


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
    if error := _validate_numeric_id(artist_id, "artist_id"):
        return error
    return await api_get(
        app_context(ctx),
        f"/api/collaborators/{artist_id}",
        {"limit": min(max(limit, 1), 100)},
    )


async def get_genre_tree(ctx: Context[AppContext, Any]) -> dict[str, Any]:
    """Get the full genre/style hierarchy from the knowledge graph.

    Returns all genres with their nested styles and release counts,
    derived from release co-occurrence. Useful for understanding the
    taxonomy of music in the database.
    """
    return await api_get(app_context(ctx), "/api/genre-tree")


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
    return await api_post(app_context(ctx), "/api/nlq/query", json_data={"query": query})


TOOL_HANDLERS = (
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
)
