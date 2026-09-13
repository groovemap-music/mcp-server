"""Regression tests for the stable MCP tool surface and shared policy delegation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_mcp_tool_names_still_exported() -> None:
    from mcp_server.server import (
        find_path,
        get_artist_details,
        get_collaborators,
        get_genre_details,
        get_genre_tree,
        get_graph_stats,
        get_label_details,
        get_release_details,
        get_style_details,
        get_trends,
        nlq_query,
        search,
    )

    for fn in (
        find_path,
        get_artist_details,
        get_collaborators,
        get_genre_details,
        get_genre_tree,
        get_graph_stats,
        get_label_details,
        get_release_details,
        get_style_details,
        get_trends,
        nlq_query,
        search,
    ):
        assert callable(fn)


@pytest.mark.asyncio
async def test_mcp_tool_input_schemas_remain_stable() -> None:
    from mcp_server.server import mcp

    expected = {
        "find_path": ({"from_name", "from_type", "to_name", "to_type", "max_depth"}, {"from_name", "from_type", "to_name", "to_type"}),
        "get_artist_details": ({"artist_id"}, {"artist_id"}),
        "get_collaborators": ({"artist_id", "limit"}, {"artist_id"}),
        "get_genre_details": ({"genre_name"}, {"genre_name"}),
        "get_genre_tree": (set(), set()),
        "get_graph_stats": (set(), set()),
        "get_label_details": ({"label_id"}, {"label_id"}),
        "get_release_details": ({"release_id"}, {"release_id"}),
        "get_style_details": ({"style_name"}, {"style_name"}),
        "get_trends": ({"name", "entity_type"}, {"name"}),
        "nlq_query": ({"query"}, {"query"}),
        "search": ({"query", "types", "media", "limit"}, {"query"}),
    }

    tools = await mcp.list_tools()
    actual = {tool.name: (set(tool.input_schema["properties"]), set(tool.input_schema.get("required", []))) for tool in tools}
    assert actual == expected

    by_name = {tool.name: tool for tool in tools}
    assert by_name["search"].input_schema["properties"]["types"]["default"] == "artist,label,master,release"
    assert by_name["search"].input_schema["properties"]["limit"]["default"] == 20
    assert by_name["find_path"].input_schema["properties"]["max_depth"]["default"] == 10
    assert by_name["get_collaborators"].input_schema["properties"]["limit"]["default"] == 20
    assert by_name["get_trends"].input_schema["properties"]["entity_type"]["default"] == "artist"


@pytest.mark.asyncio
async def test_mcp_find_path_calls_shared_tool() -> None:
    with patch("common.agent_tools.find_path", new=AsyncMock(return_value={"path": [1, 2]})) as mock:
        from mcp_server.server import find_path as mcp_find_path

        ctx = AsyncMock()
        ctx.request_context.lifespan_context = AsyncMock()

        result = await mcp_find_path(
            from_name="Kraftwerk",
            from_type="artist",
            to_name="Bambaataa",
            to_type="artist",
            ctx=ctx,
        )

        assert result == {"path": [1, 2]}
        mock.assert_awaited_once()


def test_composition_dependencies_point_toward_tool_policy() -> None:
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "mcp_server"
    server = (package / "server.py").read_text()
    routing = (package / "tool_routing.py").read_text()
    registration = (package / "registration.py").read_text()

    assert '"/api/' not in server
    assert "validate_media_filter" not in server
    assert "@mcp.tool" not in routing
    assert "import httpx" not in routing
    assert '"/api/' not in registration
