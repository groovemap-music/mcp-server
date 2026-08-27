#!/usr/bin/env bash
set -euo pipefail
bash scripts/prepare-library-wheels.sh
install_tmp="$(mktemp -d)"
trap 'rm -rf "${install_tmp}"' EXIT
uv venv "${install_tmp}/venv"
uv pip install --python "${install_tmp}/venv/bin/python" --find-links .build/libraries dist/*.whl
"${install_tmp}/venv/bin/python" -c 'from mcp_server.server import mcp; assert mcp.name == "GrooveMap"'
"${install_tmp}/venv/bin/python" - <<'PY'
import asyncio

from mcp_server.server import mcp


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
actual = {tool.name for tool in asyncio.run(mcp.list_tools())}
assert actual == expected, (actual, expected)
PY
