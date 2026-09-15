"""Tests for the MCP server tools.

All tools call the GrooveMap Catalog API via httpx instead of
accessing databases directly. Tests mock httpx responses.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_ctx():
    """Create an AppContext with a mocked httpx client."""
    from mcp_server.server import AppContext

    client = MagicMock(spec=httpx.AsyncClient)
    return AppContext(client=client, base_url="http://test-api:8004")


@pytest.fixture()
def delegated_ctx():
    """Create an AppContext that has a delegated app token configured."""
    from mcp_server.server import AppContext

    client = MagicMock(spec=httpx.AsyncClient)
    return AppContext(client=client, base_url="http://test-api:8004", app_token="app-token-value")


@pytest.fixture()
def mock_context(app_ctx):
    """Create a mock MCP Context whose lifespan_context is our AppContext."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    return ctx


@pytest.fixture()
def delegated_context(delegated_ctx):
    """Create a mock MCP Context whose lifespan_context carries a delegated app token."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = delegated_ctx
    return ctx


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with the given JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    return resp


# ---------------------------------------------------------------------------
# Tool: search
# ---------------------------------------------------------------------------


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_context, app_ctx):
        from mcp_server.server import search

        fake_response = {
            "query": "miles",
            "total": 1,
            "facets": {"type": {"artist": 1}, "genre": {}, "decade": {}},
            "results": [
                {"type": "artist", "id": "23755", "name": "Miles Davis", "highlight": "<b>Miles</b> Davis", "relevance": 0.9, "metadata": {}}
            ],
            "pagination": {"limit": 20, "offset": 0, "has_more": False},
        }

        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await search(query="miles", ctx=mock_context)

        assert result["total"] == 1
        assert result["results"][0]["name"] == "Miles Davis"
        app_ctx.client.get.assert_called_once()
        call_args = app_ctx.client.get.call_args
        assert "/api/search" in call_args.args[0]
        assert call_args.kwargs["params"]["q"] == "miles"

    @pytest.mark.asyncio
    async def test_search_invalid_type(self, mock_context):
        from mcp_server.server import search

        result = await search(query="test", types="invalid", ctx=mock_context)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_empty_types_defaults_to_all(self, mock_context, app_ctx):
        from mcp_server.server import search

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"total": 0, "results": []}))

        await search(query="test", types="", ctx=mock_context)

        call_params = app_ctx.client.get.call_args.kwargs["params"]
        # When types is empty, it should default to all valid search types
        assert "types" in call_params

    @pytest.mark.asyncio
    async def test_search_clamps_limit(self, mock_context, app_ctx):
        from mcp_server.server import search

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"total": 0, "results": []}))

        await search(query="test", limit=999, ctx=mock_context)

        call_params = app_ctx.client.get.call_args.kwargs["params"]
        assert call_params["limit"] == 100

    @pytest.mark.asyncio
    async def test_search_forwards_a_validated_media_filter(self, mock_context, app_ctx):
        """httpx serializes a list param as repeated `media` query parameters."""
        from mcp_server.server import search

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"total": 0, "results": []}))

        await search(query="test", media=["vinyl", "optical_cd"], ctx=mock_context)

        call_params = app_ctx.client.get.call_args.kwargs["params"]
        assert call_params["media"] == ["vinyl", "optical_cd"]

    @pytest.mark.asyncio
    async def test_search_omits_media_when_not_given(self, mock_context, app_ctx):
        from mcp_server.server import search

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"total": 0, "results": []}))

        await search(query="test", ctx=mock_context)

        call_params = app_ctx.client.get.call_args.kwargs["params"]
        assert "media" not in call_params

    @pytest.mark.asyncio
    async def test_search_rejects_unknown_media_id(self, mock_context, app_ctx):
        from mcp_server.server import search

        app_ctx.client.get = AsyncMock()

        result = await search(query="test", media=["laserdisk"], ctx=mock_context)

        assert "error" in result
        assert "laserdisk" in result["error"]
        assert "vinyl" in result["error"]
        app_ctx.client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_media_error_names_every_unknown_id(self, mock_context, app_ctx):
        from mcp_server.server import search

        app_ctx.client.get = AsyncMock()

        result = await search(query="test", media=["vinyl", "laserdisk", "betamax"], ctx=mock_context)

        assert "betamax" in result["error"]
        assert "laserdisk" in result["error"]
        app_ctx.client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_error_lists_the_generated_family_ids(self, mock_context, app_ctx):
        """The `Valid families` list in the error is the taxonomy's, not a hand-copied one."""
        from common.media import family_ids

        from mcp_server.server import search

        app_ctx.client.get = AsyncMock()

        result = await search(query="test", media=["laserdisk"], ctx=mock_context)

        assert f"Valid families: {', '.join(family_ids())}." in result["error"]

    @pytest.mark.asyncio
    async def test_exposed_tool_description_lists_the_generated_family_ids(self):
        """The registered MCP tool schema description must match `common.media.family_ids()`

        exactly, not a hardcoded copy that can drift from the taxonomy.
        """
        from common.media import family_ids

        from mcp_server.server import mcp

        tools = await mcp.list_tools()
        search_tool = next(t for t in tools if t.name == "search")

        assert f"Valid families: {', '.join(family_ids())}." in search_tool.description


# ---------------------------------------------------------------------------
# Tools: entity details
# ---------------------------------------------------------------------------


class TestGetArtistDetails:
    @pytest.mark.asyncio
    async def test_found(self, mock_context, app_ctx):
        from mcp_server.server import get_artist_details

        fake = {"id": "1", "name": "Miles Davis", "genres": ["Jazz"], "styles": ["Modal"], "release_count": 500, "groups": []}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake))

        result = await get_artist_details(artist_id="1", ctx=mock_context)

        assert result["name"] == "Miles Davis"
        assert result["genres"] == ["Jazz"]

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import get_artist_details

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "not found"}, status_code=404))

        result = await get_artist_details(artist_id="999", ctx=mock_context)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_rejects_non_numeric_id(self, mock_context, app_ctx):
        from mcp_server.server import get_artist_details

        app_ctx.client.get = AsyncMock()

        result = await get_artist_details(artist_id="../../admin", ctx=mock_context)

        assert "error" in result
        assert "must be a numeric string" in result["error"]
        app_ctx.client.get.assert_not_called()


class TestGetLabelDetails:
    @pytest.mark.asyncio
    async def test_found(self, mock_context, app_ctx):
        from mcp_server.server import get_label_details

        fake = {"id": "1", "name": "Blue Note", "release_count": 5000}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake))

        result = await get_label_details(label_id="1", ctx=mock_context)

        assert result["name"] == "Blue Note"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import get_label_details

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "not found"}, status_code=404))

        result = await get_label_details(label_id="999", ctx=mock_context)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_rejects_non_numeric_id(self, mock_context, app_ctx):
        from mcp_server.server import get_label_details

        app_ctx.client.get = AsyncMock()

        result = await get_label_details(label_id="abc", ctx=mock_context)

        assert "error" in result
        assert "must be a numeric string" in result["error"]
        app_ctx.client.get.assert_not_called()


class TestGetReleaseDetails:
    @pytest.mark.asyncio
    async def test_found(self, mock_context, app_ctx):
        from mcp_server.server import get_release_details

        fake = {
            "id": "1",
            "name": "Kind of Blue",
            "year": 1959,
            "artists": ["Miles Davis"],
            "labels": ["Columbia"],
            "genres": ["Jazz"],
            "styles": ["Modal"],
        }
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake))

        result = await get_release_details(release_id="1", ctx=mock_context)

        assert result["name"] == "Kind of Blue"
        assert result["year"] == 1959

    @pytest.mark.asyncio
    async def test_passes_through_the_media_block_unaltered(self, mock_context, app_ctx):
        """The tool is a pass-through: an ADR 0007 media block from the API reaches the caller as-is."""
        from mcp_server.server import get_release_details

        media_block = {
            "taxonomy_version": "1",
            "items": [
                {
                    "family": "vinyl",
                    "medium": "vinyl_12",
                    "qty": 1,
                    "size_inches": 12,
                    "speed_rpm": 33,
                    "channels": "stereo",
                    "codec": None,
                    "variants": [],
                    "appearance": [],
                    "position": None,
                    "track_count": None,
                    "source": {"provider": "discogs", "name": "Vinyl", "descriptions": ["LP"], "text": None},
                }
            ],
            "families": ["vinyl"],
            "release_kind": "album",
            "traits": [],
            "edition": [],
            "packaging": None,
            "container": None,
            "flags": [],
            "unmapped": {"formats": [], "descriptions": []},
        }
        fake = {"id": "1", "name": "Kind of Blue", "media": media_block}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake))

        result = await get_release_details(release_id="1", ctx=mock_context)

        assert result["media"] == media_block

    def test_docstring_documents_the_media_block_shape(self):
        """The documented fields must match `common.agent_tools.schemas.MediaBlock`."""
        from mcp_server.server import get_release_details

        doc = get_release_details.__doc__ or ""
        for field in ("media", "families", "items", "release_kind", "edition", "unmapped"):
            assert field in doc, f"get_release_details docstring is missing the `{field}` field"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import get_release_details

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "not found"}, status_code=404))

        result = await get_release_details(release_id="999", ctx=mock_context)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_rejects_non_numeric_id(self, mock_context, app_ctx):
        from mcp_server.server import get_release_details

        app_ctx.client.get = AsyncMock()

        result = await get_release_details(release_id="abc", ctx=mock_context)

        assert "error" in result
        assert "must be a numeric string" in result["error"]
        app_ctx.client.get.assert_not_called()


class TestGetGenreDetails:
    @pytest.mark.asyncio
    async def test_found(self, mock_context, app_ctx):
        from mcp_server.server import get_genre_details

        fake = {"id": "Jazz", "name": "Jazz", "artist_count": 50000}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake))

        result = await get_genre_details(genre_name="Jazz", ctx=mock_context)

        assert result["name"] == "Jazz"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import get_genre_details

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "not found"}, status_code=404))

        result = await get_genre_details(genre_name="Nonexistent", ctx=mock_context)

        assert "error" in result


class TestGetStyleDetails:
    @pytest.mark.asyncio
    async def test_found(self, mock_context, app_ctx):
        from mcp_server.server import get_style_details

        fake = {"id": "Acid Jazz", "name": "Acid Jazz", "artist_count": 2000}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake))

        result = await get_style_details(style_name="Acid Jazz", ctx=mock_context)

        assert result["name"] == "Acid Jazz"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import get_style_details

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "not found"}, status_code=404))

        result = await get_style_details(style_name="Nonexistent", ctx=mock_context)

        assert "error" in result


# ---------------------------------------------------------------------------
# Tool: find_path
# ---------------------------------------------------------------------------


class TestFindPath:
    @pytest.mark.asyncio
    async def test_path_found(self, mock_context, app_ctx):
        from mcp_server.server import find_path

        fake_response = {
            "found": True,
            "length": 2,
            "path": [
                {"id": "1", "name": "Miles Davis", "type": "artist", "rel": None},
                {"id": "201", "name": "Kind of Blue", "type": "release", "rel": "BY"},
                {"id": "2", "name": "Daft Punk", "type": "artist", "rel": "BY"},
            ],
        }

        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await find_path(from_name="Miles Davis", from_type="artist", to_name="Daft Punk", to_type="artist", ctx=mock_context)

        assert result["found"] is True
        assert result["length"] == 2
        assert len(result["path"]) == 3
        assert result["path"][0]["name"] == "Miles Davis"
        assert result["path"][0]["rel"] is None
        assert result["path"][1]["rel"] == "BY"

    @pytest.mark.asyncio
    async def test_path_not_found(self, mock_context, app_ctx):
        from mcp_server.server import find_path

        fake_response = {"found": False, "length": None, "path": []}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await find_path(from_name="A", from_type="artist", to_name="B", to_type="artist", ctx=mock_context)

        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_invalid_from_type(self, mock_context):
        from mcp_server.server import find_path

        result = await find_path(from_name="X", from_type="invalid", to_name="Y", to_type="artist", ctx=mock_context)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_to_type(self, mock_context):
        from mcp_server.server import find_path

        result = await find_path(from_name="X", from_type="artist", to_name="Y", to_type="invalid", ctx=mock_context)
        assert "error" in result
        assert "to_type" in result["error"]

    @pytest.mark.asyncio
    async def test_entity_not_found(self, mock_context, app_ctx):
        from mcp_server.server import find_path

        fake_response = {"error": "Artist 'Nobody' not found"}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response, status_code=404))

        result = await find_path(from_name="Nobody", from_type="artist", to_name="Y", to_type="artist", ctx=mock_context)

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_max_depth_above_api_ceiling_is_clamped_to_10(self, mock_context, app_ctx):
        """Regression: the tool used to clamp to 15 while the API's
        _MAX_PATH_DEPTH is 10 (Query(..., le=10)), so max_depth=11-15 always got
        forwarded and always 422'd. It must now be clamped to the API's real ceiling.
        """
        from mcp_server.server import find_path

        fake_response = {"found": True, "length": 1, "path": []}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        await find_path(from_name="Kraftwerk", from_type="artist", to_name="Afrika Bambaataa", to_type="artist", max_depth=12, ctx=mock_context)

        _, call_kwargs = app_ctx.client.get.call_args
        assert call_kwargs["params"]["max_depth"] == 10

    @pytest.mark.asyncio
    async def test_max_depth_non_digit_falls_back_to_documented_default(self, mock_context, app_ctx):
        """Regression: the non-digit fallback used to be 3, contradicting the
        documented/signature default of 10.
        """
        from mcp_server.server import find_path

        fake_response = {"found": True, "length": 1, "path": []}
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        await find_path(from_name="A", from_type="artist", to_name="B", to_type="artist", max_depth="not-a-number", ctx=mock_context)

        _, call_kwargs = app_ctx.client.get.call_args
        assert call_kwargs["params"]["max_depth"] == 10


# ---------------------------------------------------------------------------
# Tool: get_trends
# ---------------------------------------------------------------------------


class TestGetTrends:
    @pytest.mark.asyncio
    async def test_returns_data(self, mock_context, app_ctx):
        from mcp_server.server import get_trends

        fake_response = {
            "name": "Miles Davis",
            "type": "artist",
            "data": [{"year": 1959, "count": 3}, {"year": 1960, "count": 5}],
        }

        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await get_trends(name="Miles Davis", entity_type="artist", ctx=mock_context)

        assert result["name"] == "Miles Davis"
        assert result["type"] == "artist"
        assert len(result["data"]) == 2

    @pytest.mark.asyncio
    async def test_invalid_type(self, mock_context):
        from mcp_server.server import get_trends

        result = await get_trends(name="X", entity_type="invalid", ctx=mock_context)
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool: get_graph_stats
# ---------------------------------------------------------------------------


class TestGetGraphStats:
    @pytest.mark.asyncio
    async def test_returns_counts(self, mock_context, app_ctx):
        from mcp_server.server import get_graph_stats

        fake_response = {
            "total_entities": 8815,
            "counts": {
                "artists": 1000,
                "labels": 500,
                "releases": 5000,
                "masters": 2000,
                "genres": 15,
                "styles": 300,
            },
        }

        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await get_graph_stats(ctx=mock_context)

        assert result["total_entities"] == 8815
        assert result["counts"]["artists"] == 1000
        assert result["counts"]["releases"] == 5000
        assert result["counts"]["genres"] == 15


# ---------------------------------------------------------------------------
# Tool: get_collaborators
# ---------------------------------------------------------------------------


class TestGetCollaborators:
    @pytest.mark.asyncio
    async def test_returns_collaborators(self, mock_context, app_ctx):
        from mcp_server.server import get_collaborators

        fake_response = {
            "artist_id": "1",
            "artist_name": "Miles Davis",
            "collaborators": [
                {"artist_id": "2", "artist_name": "John Coltrane", "release_count": 5},
            ],
            "total": 42,
        }

        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await get_collaborators(artist_id="1", ctx=mock_context)

        assert result["artist_name"] == "Miles Davis"
        assert result["total"] == 42
        assert len(result["collaborators"]) == 1

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import get_collaborators

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "not found"}, status_code=404))

        result = await get_collaborators(artist_id="999", ctx=mock_context)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_clamps_limit(self, mock_context, app_ctx):
        from mcp_server.server import get_collaborators

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"collaborators": [], "total": 0}))

        await get_collaborators(artist_id="1", limit=999, ctx=mock_context)

        call_params = app_ctx.client.get.call_args.kwargs["params"]
        assert call_params["limit"] == 100

    @pytest.mark.asyncio
    async def test_rejects_non_numeric_id(self, mock_context, app_ctx):
        from mcp_server.server import get_collaborators

        app_ctx.client.get = AsyncMock()

        result = await get_collaborators(artist_id="../../admin", ctx=mock_context)

        assert "error" in result
        assert "must be a numeric string" in result["error"]
        app_ctx.client.get.assert_not_called()


# ---------------------------------------------------------------------------
# Tool: get_genre_tree
# ---------------------------------------------------------------------------


class TestGetGenreTree:
    @pytest.mark.asyncio
    async def test_returns_tree(self, mock_context, app_ctx):
        from mcp_server.server import get_genre_tree

        fake_response = {
            "genres": [
                {"name": "Rock", "release_count": 1000, "styles": [{"name": "Punk", "release_count": 200}]},
                {"name": "Jazz", "release_count": 500, "styles": []},
            ],
        }

        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await get_genre_tree(ctx=mock_context)

        assert len(result["genres"]) == 2
        assert result["genres"][0]["name"] == "Rock"
        assert result["genres"][0]["styles"][0]["name"] == "Punk"


# ---------------------------------------------------------------------------
# Tool: lookup_release
# ---------------------------------------------------------------------------


class TestLookupRelease:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider", ["barcode", "catalog_number", "matrix"])
    async def test_resolves_each_documented_provider(self, mock_context, app_ctx, provider):
        from mcp_server.server import lookup_release

        fake_response = {
            "provider": provider,
            "value": "012345678905",
            "normalized": "012345678905",
            "gm_id": "1",
            "releases": [{"id": "1", "name": "Kind of Blue"}],
        }
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await lookup_release(provider=provider, value="012345678905", ctx=mock_context)

        assert result == fake_response
        assert app_ctx.client.get.call_args.args[0] == f"http://test-api:8004/api/lookup/{provider}/012345678905"

    @pytest.mark.asyncio
    async def test_url_quotes_the_value(self, mock_context, app_ctx):
        from mcp_server.server import lookup_release

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"releases": []}))

        await lookup_release(provider="matrix", value="A1/B1 side", ctx=mock_context)

        assert app_ctx.client.get.call_args.args[0] == "http://test-api:8004/api/lookup/matrix/A1%2FB1%20side"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_context, app_ctx):
        from mcp_server.server import lookup_release

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"error": "No release found for barcode '000'"}, status_code=404))

        result = await lookup_release(provider="barcode", value="000", ctx=mock_context)

        assert "error" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider", ["label_code", "BARCODE", "../admin", ""])
    async def test_an_unknown_provider_never_reaches_the_api(self, mock_context, app_ctx, provider):
        from mcp_server.server import lookup_release

        app_ctx.client.get = AsyncMock()

        result = await lookup_release(provider=provider, value="012345678905", ctx=mock_context)

        assert "Invalid provider" in result["error"]
        app_ctx.client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_no_authorization_header_even_when_delegation_is_configured(self, delegated_context, delegated_ctx):
        """Public route: a configured app token must never reach `lookup_release`."""
        from mcp_server.server import lookup_release

        delegated_ctx.client.get = AsyncMock(return_value=_mock_response({"releases": []}))

        await lookup_release(provider="barcode", value="012345678905", ctx=delegated_context)

        assert "headers" not in delegated_ctx.client.get.call_args.kwargs


# ---------------------------------------------------------------------------
# Helper: _api_get
# ---------------------------------------------------------------------------


class TestApiGet:
    @pytest.mark.asyncio
    async def test_api_get_constructs_url(self, app_ctx):
        from mcp_server.catalog_api import api_get as _api_get

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"ok": True}))

        await _api_get(app_ctx, "/api/test", {"key": "value"})

        app_ctx.client.get.assert_called_once_with(
            "http://test-api:8004/api/test",
            params={"key": "value"},
        )

    @pytest.mark.asyncio
    async def test_api_get_http_error_returns_error_dict(self, app_ctx):
        """HTTP error response (e.g. 500) returns error dict instead of raising."""
        from mcp_server.catalog_api import api_get as _api_get

        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 500
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=error_response,
        )
        app_ctx.client.get = AsyncMock(return_value=error_response)

        result = await _api_get(app_ctx, "/api/test")

        assert "error" in result
        assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_api_get_network_error_returns_error_dict(self, app_ctx):
        """Network error (e.g. ConnectError) returns error dict instead of raising."""
        from mcp_server.catalog_api import api_get as _api_get

        app_ctx.client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await _api_get(app_ctx, "/api/test")

        assert "error" in result
        assert "Connection refused" in result["error"]


class TestApiPost:
    @pytest.mark.asyncio
    async def test_api_post_http_error_returns_error_dict(self, app_ctx):
        """HTTP error response from POST returns error dict."""
        from mcp_server.catalog_api import api_post as _api_post

        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 500
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=error_response,
        )
        app_ctx.client.post = AsyncMock(return_value=error_response)

        result = await _api_post(app_ctx, "/api/test", json_data={"query": "test"})

        assert "error" in result
        assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_api_post_network_error_returns_error_dict(self, app_ctx):
        """Network error from POST returns error dict."""
        from mcp_server.catalog_api import api_post as _api_post

        app_ctx.client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await _api_post(app_ctx, "/api/test", json_data={"query": "test"})

        assert "error" in result
        assert "Connection refused" in result["error"]


# ---------------------------------------------------------------------------
# Delegated tools: record_recommendation_outcome, get_consent, set_consent
# ---------------------------------------------------------------------------


class TestRecordRecommendationOutcome:
    @pytest.mark.asyncio
    async def test_posts_the_prefixed_event_type_with_both_ids(self, delegated_context, delegated_ctx):
        from mcp_server.server import record_recommendation_outcome

        accepted = {"recorded": True, "event_type": "recommendation.saved", "impression_id": "imp-1"}
        delegated_ctx.client.post = AsyncMock(return_value=_mock_response(accepted))

        result = await record_recommendation_outcome(
            impression_id="imp-1",
            item_id="item-9",
            outcome="saved",
            ctx=delegated_context,
        )

        assert result == accepted
        assert delegated_ctx.client.post.call_args.args[0] == "http://test-api:8004/api/activity/events"
        assert delegated_ctx.client.post.call_args.kwargs["json"] == {
            "event_type": "recommendation.saved",
            "impression_id": "imp-1",
            "item_id": "item-9",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome", ["opened", "saved", "dismissed", "hidden"])
    async def test_every_documented_outcome_is_accepted(self, delegated_context, delegated_ctx, outcome):
        from mcp_server.server import record_recommendation_outcome

        delegated_ctx.client.post = AsyncMock(return_value=_mock_response({"recorded": True}))

        await record_recommendation_outcome(impression_id="i", item_id="x", outcome=outcome, ctx=delegated_context)

        assert delegated_ctx.client.post.call_args.kwargs["json"]["event_type"] == f"recommendation.{outcome}"

    @pytest.mark.asyncio
    async def test_outcome_is_matched_case_insensitively(self, delegated_context, delegated_ctx):
        from mcp_server.server import record_recommendation_outcome

        delegated_ctx.client.post = AsyncMock(return_value=_mock_response({"recorded": True}))

        await record_recommendation_outcome(impression_id="i", item_id="x", outcome="Opened", ctx=delegated_context)

        assert delegated_ctx.client.post.call_args.kwargs["json"]["event_type"] == "recommendation.opened"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome", ["shown", "clicked", "recommendation.opened", ""])
    async def test_a_value_outside_the_four_outcomes_never_reaches_the_api(self, delegated_context, delegated_ctx, outcome):
        """The producer answers a bad enum with a 422; it should never have to."""
        from mcp_server.server import record_recommendation_outcome

        delegated_ctx.client.post = AsyncMock()

        result = await record_recommendation_outcome(impression_id="i", item_id="x", outcome=outcome, ctx=delegated_context)

        assert "Invalid outcome" in result["error"]
        delegated_ctx.client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_declines_without_a_token_and_records_nothing(self, mock_context, app_ctx):
        from mcp_server.catalog_api import DELEGATION_NOT_CONFIGURED
        from mcp_server.server import record_recommendation_outcome

        app_ctx.client.post = AsyncMock()

        result = await record_recommendation_outcome(impression_id="i", item_id="x", outcome="opened", ctx=mock_context)

        assert result["error"] == DELEGATION_NOT_CONFIGURED
        app_ctx.client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_upstream_failure_is_returned_as_a_structured_error(self, delegated_context, delegated_ctx):
        from mcp_server.server import record_recommendation_outcome

        delegated_ctx.client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await record_recommendation_outcome(impression_id="i", item_id="x", outcome="opened", ctx=delegated_context)

        assert "Connection refused" in result["error"]


class TestGetConsent:
    @pytest.mark.asyncio
    async def test_returns_the_api_response_verbatim(self, delegated_context, delegated_ctx):
        from mcp_server.server import get_consent

        state = {
            "purposes": [
                {"purpose": "product_analytics", "granted": True, "granted_at": "2026-01-01T00:00:00Z", "revoked_at": None},
                {"purpose": "model_training", "granted": False, "granted_at": None, "revoked_at": None},
            ]
        }
        delegated_ctx.client.get = AsyncMock(return_value=_mock_response(state))

        result = await get_consent(ctx=delegated_context)

        assert result == state
        assert delegated_ctx.client.get.call_args.args[0] == "http://test-api:8004/api/user/consent"

    @pytest.mark.asyncio
    async def test_declines_without_a_token(self, mock_context, app_ctx):
        from mcp_server.catalog_api import DELEGATION_NOT_CONFIGURED
        from mcp_server.server import get_consent

        app_ctx.client.get = AsyncMock()

        result = await get_consent(ctx=mock_context)

        assert result["error"] == DELEGATION_NOT_CONFIGURED
        app_ctx.client.get.assert_not_called()


class TestSetConsent:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("purpose", ["product_analytics", "model_training"])
    @pytest.mark.parametrize("granted", [True, False])
    async def test_puts_the_decision_on_the_purpose_route(self, delegated_context, delegated_ctx, purpose, granted):
        from mcp_server.server import set_consent

        delegated_ctx.client.put = AsyncMock(return_value=_mock_response({"purpose": purpose, "granted": granted, "changed": True}))

        result = await set_consent(purpose=purpose, granted=granted, ctx=delegated_context)

        assert result == {"purpose": purpose, "granted": granted, "changed": True}
        assert delegated_ctx.client.put.call_args.args[0] == f"http://test-api:8004/api/user/consent/{purpose}"
        assert delegated_ctx.client.put.call_args.kwargs["json"] == {"granted": granted}

    @pytest.mark.asyncio
    async def test_the_delegated_put_carries_the_bearer_token(self, delegated_context, delegated_ctx):
        from mcp_server.server import set_consent

        delegated_ctx.client.put = AsyncMock(return_value=_mock_response({"changed": False}))

        await set_consent(purpose="model_training", granted=False, ctx=delegated_context)

        assert delegated_ctx.client.put.call_args.kwargs["headers"] == {"Authorization": "Bearer app-token-value"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("purpose", ["marketing", "PRODUCT_ANALYTICS", "../admin", ""])
    async def test_a_purpose_outside_the_vocabulary_never_reaches_the_api(self, delegated_context, delegated_ctx, purpose):
        from mcp_server.server import set_consent

        delegated_ctx.client.put = AsyncMock()

        result = await set_consent(purpose=purpose, granted=True, ctx=delegated_context)

        assert "Invalid purpose" in result["error"]
        delegated_ctx.client.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_declines_without_a_token_and_changes_nothing(self, mock_context, app_ctx):
        from mcp_server.catalog_api import DELEGATION_NOT_CONFIGURED
        from mcp_server.server import set_consent

        app_ctx.client.put = AsyncMock()

        result = await set_consent(purpose="product_analytics", granted=True, ctx=mock_context)

        assert result["error"] == DELEGATION_NOT_CONFIGURED
        app_ctx.client.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_argument_check_runs_before_the_delegation_check(self, mock_context, app_ctx):
        """A bad enum is the tool's own answer whether or not delegation is configured."""
        from mcp_server.server import set_consent

        app_ctx.client.put = AsyncMock()

        result = await set_consent(purpose="marketing", granted=True, ctx=mock_context)

        assert "Invalid purpose" in result["error"]


class TestDelegatedToolVocabulary:
    def test_the_consent_purposes_come_from_the_published_vocabulary(self):
        from common.events import consent_purposes

        from mcp_server.tool_routing import _CONSENT_PURPOSES

        assert consent_purposes() == _CONSENT_PURPOSES

    def test_every_outcome_maps_to_a_published_event_type(self):
        """`recommendation.<outcome>` must be a real event type, and `shown` is not an outcome."""
        from common.events import event_types

        from mcp_server.tool_routing import _RECOMMENDATION_OUTCOMES

        published = set(event_types())
        assert all(f"recommendation.{outcome}" in published for outcome in _RECOMMENDATION_OUTCOMES)
        assert "shown" not in _RECOMMENDATION_OUTCOMES

    def test_erasure_and_export_are_not_exposed_as_tools(self):
        """The routes are promoted; the tools deliberately are not."""
        from mcp_server.tool_routing import TOOL_HANDLERS

        routing = (Path(__file__).resolve().parents[1] / "mcp_server/tool_routing.py").read_text()

        assert "/api/user/erasure" not in routing
        assert "/api/user/export" not in routing
        assert not any("erasure" in handler.__name__ or "export" in handler.__name__ for handler in TOOL_HANDLERS)


# ---------------------------------------------------------------------------
# Delegated app token boundary
# ---------------------------------------------------------------------------


class TestDelegatedTokenBoundary:
    """Where the bearer header goes, where it does not, and what it never reaches."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["/api/search", "/api/graph/stats", "/api/node/12345", "/api/user/export", "/api/lookup/barcode/012345678905"])
    async def test_public_routes_send_no_authorization_header(self, delegated_ctx, path):
        """A configured token changes nothing about a catalog route's request."""
        from mcp_server.catalog_api import api_get

        delegated_ctx.client.get = AsyncMock(return_value=_mock_response({"ok": True}))

        await api_get(delegated_ctx, path)

        assert "headers" not in delegated_ctx.client.get.call_args.kwargs

    @pytest.mark.asyncio
    async def test_delegated_get_route_carries_the_bearer_token(self, delegated_ctx):
        from mcp_server.catalog_api import api_get

        delegated_ctx.client.get = AsyncMock(return_value=_mock_response({"purposes": []}))

        await api_get(delegated_ctx, "/api/user/consent")

        assert delegated_ctx.client.get.call_args.kwargs["headers"] == {"Authorization": "Bearer app-token-value"}

    @pytest.mark.asyncio
    async def test_delegated_post_route_carries_the_bearer_token(self, delegated_ctx):
        from mcp_server.catalog_api import api_post

        delegated_ctx.client.post = AsyncMock(return_value=_mock_response({"recorded": True}))

        await api_post(delegated_ctx, "/api/activity/events", json_data={"event_type": "recommendation.opened"})

        assert delegated_ctx.client.post.call_args.kwargs["headers"] == {"Authorization": "Bearer app-token-value"}

    @pytest.mark.asyncio
    async def test_delegated_route_sends_nothing_when_no_token_is_configured(self, app_ctx):
        """Without a token the request still goes out unauthenticated rather than half-signed."""
        from mcp_server.catalog_api import api_get

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"purposes": []}))

        await api_get(app_ctx, "/api/user/consent")

        assert "headers" not in app_ctx.client.get.call_args.kwargs

    @pytest.mark.asyncio
    async def test_a_neighbouring_path_does_not_inherit_the_header(self, delegated_ctx):
        """The delegated route set is matched whole, so no longer path picks the token up."""
        from mcp_server.catalog_api import api_get

        delegated_ctx.client.get = AsyncMock(return_value=_mock_response({"ok": True}))

        await api_get(delegated_ctx, "/api/user/consent/product_analytics/history")

        assert "headers" not in delegated_ctx.client.get.call_args.kwargs

    def test_delegation_error_is_absent_when_a_token_is_configured(self, delegated_ctx):
        from mcp_server.catalog_api import delegation_error

        assert delegation_error(delegated_ctx) is None

    def test_delegation_error_names_the_setting_and_never_a_value(self, app_ctx):
        from mcp_server.catalog_api import DELEGATION_NOT_CONFIGURED, delegation_error

        error = delegation_error(app_ctx)

        assert error is not None
        assert error["error"] == DELEGATION_NOT_CONFIGURED
        assert "GROOVEMAP_CATALOG_APP_TOKEN" in error["detail"]

    def test_delegation_error_is_a_fresh_mapping_per_call(self, app_ctx):
        """A caller that annotates the refusal cannot change the next caller's refusal."""
        from mcp_server.catalog_api import delegation_error

        first = delegation_error(app_ctx)
        assert first is not None
        first["error"] = "mutated"

        second = delegation_error(app_ctx)
        assert second is not None
        assert second["error"] != "mutated"

    @pytest.mark.asyncio
    async def test_an_upstream_failure_never_reports_the_token(self, delegated_ctx):
        """The error mapping returns the URL and the status, and nothing about the credential."""
        from mcp_server.catalog_api import api_get

        delegated_ctx.client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await api_get(delegated_ctx, "/api/user/consent")

        assert "app-token-value" not in repr(result)
        assert "Authorization" not in repr(result)


class TestLifespanTokenSource:
    @pytest.mark.asyncio
    async def test_lifespan_reads_the_token_from_the_environment(self, monkeypatch):
        from mcp_server.server import app_lifespan

        monkeypatch.setenv("GROOVEMAP_CATALOG_APP_TOKEN", "from-the-environment")
        async with app_lifespan(MagicMock()) as app:
            assert app.app_token == "from-the-environment"

    @pytest.mark.asyncio
    async def test_lifespan_leaves_the_token_unset_when_the_variable_is_absent(self, monkeypatch):
        from mcp_server.server import app_lifespan

        monkeypatch.delenv("GROOVEMAP_CATALOG_APP_TOKEN", raising=False)
        async with app_lifespan(MagicMock()) as app:
            assert app.app_token is None

    @pytest.mark.asyncio
    async def test_an_empty_variable_is_not_a_token(self, monkeypatch):
        """An exported-but-empty variable is a deployment that did not configure delegation."""
        from mcp_server.server import app_lifespan

        monkeypatch.setenv("GROOVEMAP_CATALOG_APP_TOKEN", "")
        async with app_lifespan(MagicMock()) as app:
            assert app.app_token is None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_parses_transport(self):
        """Verify main() parses --transport and calls mcp.run()."""
        from mcp_server.server import main

        with patch("mcp_server.server.mcp") as mock_mcp, patch("sys.argv", ["groovemap-mcp", "--transport", "streamable-http"]):
            main()
            mock_mcp.run.assert_called_once_with(transport="streamable-http")

    def test_main_default_stdio(self):
        from mcp_server.server import main

        with patch("mcp_server.server.mcp") as mock_mcp, patch("sys.argv", ["groovemap-mcp"]):
            main()
            mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_main_transport_equals_syntax(self):
        from mcp_server.server import main

        with patch("mcp_server.server.mcp") as mock_mcp, patch("sys.argv", ["groovemap-mcp", "--transport=streamable-http"]):
            main()
            mock_mcp.run.assert_called_once_with(transport="streamable-http")

    def test_main_invalid_transport_falls_back_to_stdio(self):
        from mcp_server.server import main

        with patch("mcp_server.server.mcp") as mock_mcp, patch("sys.argv", ["groovemap-mcp", "--transport", "invalid"]):
            main()
            mock_mcp.run.assert_called_once_with(transport="stdio")
