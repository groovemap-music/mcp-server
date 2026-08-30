"""Compatibility checks for the promoted Catalog API contract and MCP surface."""

import asyncio
import hashlib
import json
from dataclasses import fields
from pathlib import Path

from mcp_server.server import AppContext, mcp


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


def test_lifespan_context_has_no_credential_contract() -> None:
    """The public Catalog API adapter does not claim or carry a token."""
    assert [field.name for field in fields(AppContext)] == ["client", "base_url"]


def test_documented_launch_paths_use_the_project_environment() -> None:
    """Setup must be followed by an executable uv-managed entry point."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    configuration = (ROOT / "docs/configuration.md").read_text(encoding="utf-8")

    assert "API_BASE_URL=http://localhost:8004 uv run groovemap-mcp" in readme
    assert "API_BASE_URL=http://localhost:8004 uv run groovemap-mcp" in configuration

    client_config = json.loads(readme.split("```json\n", 1)[1].split("\n```", 1)[0])
    server_config = client_config["mcpServers"]["groovemap"]
    assert server_config["command"] == "uv"
    assert server_config["args"] == ["--project", "/absolute/path/to/mcp-server", "run", "groovemap-mcp"]


def test_documented_catalog_boundary_matches_promoted_contract() -> None:
    """The adapter's current upstream boundary is explicitly public and tokenless."""
    architecture = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    security = (ROOT / "docs/security.md").read_text(encoding="utf-8")

    assert "public, no-token Catalog API routes" in " ".join(architecture.split())
    assert "public, no-token Catalog API routes" in " ".join(security.split())
