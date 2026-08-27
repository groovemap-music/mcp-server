"""Compatibility checks for the promoted Catalog API contract and MCP surface."""

import asyncio
import hashlib
import json
from pathlib import Path

from mcp_server.server import mcp


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts/catalog-api/mcp-server/v1"


def test_promoted_contract_has_verified_provenance() -> None:
    contract_path = CONTRACT_ROOT / "routes.json"
    contract = json.loads(contract_path.read_text())
    source = json.loads((CONTRACT_ROOT / "source.json").read_text())

    assert source["version"] == contract["version"] == 1
    assert len(source["producer_commit"]) == 40
    assert hashlib.sha256(contract_path.read_bytes()).hexdigest() == source["contract_sha256"]


def test_public_mcp_tool_surface_is_stable() -> None:
    expected = {
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
        "nlq_query",
        "search",
    }

    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == expected
    assert all("ctx" not in tool.input_schema.get("properties", {}) for tool in tools)
