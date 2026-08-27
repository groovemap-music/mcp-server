"""Verify promoted Catalog API routes cover every endpoint used by the MCP adapter."""

import ast
import json
import re
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts/catalog-api/mcp-server/v1"
source = json.loads((CONTRACT_ROOT / "source.json").read_text())
contract_path = CONTRACT_ROOT / "routes.json"
contract = json.loads(contract_path.read_text())
assert sha256(contract_path.read_bytes()).hexdigest() == source["contract_sha256"]
assert source["version"] == contract["version"] == 1
assert len(source["producer_commit"]) == 40


def route_pattern(path: str) -> re.Pattern[str]:
    pieces = re.split(r"(\{[^}]+\})", path)
    return re.compile("^" + "".join("[^/]+" if piece.startswith("{") else re.escape(piece) for piece in pieces) + "$")


patterns = [route_pattern(operation["path"]) for operation in contract["operations"].values()]
tree = ast.parse((ROOT / "mcp_server/server.py").read_text())
parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
used: set[str] = set()
for node in ast.walk(tree):
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/api/")
        and not isinstance(parents.get(node), ast.JoinedStr)
    ):
        used.add(node.value)
    elif isinstance(node, ast.JoinedStr):
        path = "".join(part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "value" for part in node.values)
        if path.startswith("/api/"):
            used.add(path)
assert used
for path in sorted(used):
    assert any(pattern.fullmatch(path) for pattern in patterns), f"uncontracted Catalog API route: {path}"
