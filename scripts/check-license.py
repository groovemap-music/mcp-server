"""Validate the MIT license and synchronized package version."""

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "pyproject.toml").open("rb") as source:
    project = tomllib.load(source)["project"]
version_match = re.search(r'^__version__ = "([^"]+)"$', (ROOT / "mcp_server/__init__.py").read_text(), re.MULTILINE)
assert version_match is not None
assert project["license"] == "MIT"
assert project["version"] == version_match.group(1)
license_text = (ROOT / "LICENSE").read_text()
assert "MIT License" in license_text
assert "Copyright (c) 2023-2026 Robert Wlodarczyk" in license_text
