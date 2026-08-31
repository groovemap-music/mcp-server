#!/usr/bin/env python3
"""Validate the public MCP documentation without making network requests."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^]]*]\(([^)]+)\)")
FENCE = re.compile(r"^```(?P<language>[^\s`]*)\s*$")
DIAGRAM_PREFIXES = ("flowchart ", "graph ", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")
LEGACY_BRAND = "discogs" + "ography"
PUBLIC_TOOL_NAMES = {
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
SHARED_EMOJI_GUIDE = "https://github.com/groovemap-music/.github/blob/main/docs/emoji-guide.md"


def markdown_files() -> list[Path]:
    """Return every public Markdown document in a deterministic order."""
    root_documents = sorted(path for path in ROOT.glob("*.md") if path.name != "AGENTS.md")
    return [*root_documents, *sorted((ROOT / "docs").rglob("*.md"))]


def validate_local_links(path: Path, text: str) -> list[str]:
    """Return errors for missing or escaping repository-local Markdown links."""
    errors: list[str] = []
    for raw_target in MARKDOWN_LINK.findall(text):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
        resolved = (path.parent / relative).resolve()
        if not resolved.is_relative_to(ROOT):
            errors.append(f"{path.relative_to(ROOT)}: local link escapes repository: {target}")
        elif not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing local link target: {target}")
    return errors


def validate_diagram_fences(path: Path, text: str) -> list[str]:
    """Require diagram declarations to use Mermaid fences."""
    errors: list[str] = []
    in_fence = False
    language = ""
    for line_number, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if match:
            if in_fence:
                in_fence = False
                language = ""
            else:
                in_fence = True
                language = match.group("language")
            continue
        if in_fence and line.strip().startswith(DIAGRAM_PREFIXES) and language != "mermaid":
            errors.append(f"{path.relative_to(ROOT)}:{line_number}: diagram must use a mermaid fence")
    return errors


def main() -> int:
    """Validate links, branding, and diagram fences across the documentation surface."""
    errors: list[str] = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        errors.extend(validate_local_links(path, text))
        errors.extend(validate_diagram_fences(path, text))
        if LEGACY_BRAND in text.casefold():
            errors.append(f"{path.relative_to(ROOT)}: legacy project branding is not allowed")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    tool_reference = (ROOT / "docs/tools.md").read_text(encoding="utf-8")
    for tool_name in sorted(PUBLIC_TOOL_NAMES):
        if f"`{tool_name}`" not in readme:
            errors.append(f"README.md: missing public tool: {tool_name}")
        if f"`{tool_name}`" not in tool_reference:
            errors.append(f"docs/tools.md: missing public tool: {tool_name}")
    for required_term in ("`stdio`", "Streamable HTTP", "authentication", "just check"):
        if required_term not in readme:
            errors.append(f"README.md: missing required documentation term: {required_term}")
    if SHARED_EMOJI_GUIDE not in readme:
        errors.append("README.md: missing the public shared logging emoji guide")
    if (ROOT / "docs/extraction.md").exists():
        errors.append("docs/extraction.md: private extraction provenance must not be published")
    for required_document in ("docs/release-compliance.md", "docs/history-rewrite-gate.md"):
        if required_document not in readme:
            errors.append(f"README.md: missing publication document: {required_document}")
    for launch_fragment in ('"command": "uv"', '"--project"', '"run"', '"groovemap-mcp"'):
        if launch_fragment not in readme:
            errors.append(f"README.md: incomplete uv client launch configuration: {launch_fragment}")
    if '"command": "groovemap-mcp"' in readme:
        errors.append("README.md: client launch bypasses the project environment")
    for path in (ROOT / "README.md", ROOT / "docs/configuration.md"):
        text = path.read_text(encoding="utf-8")
        if "uv run groovemap-mcp" not in text:
            errors.append(f"{path.relative_to(ROOT)}: missing executable uv run example")

    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Documentation validation passed ({len(markdown_files())} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
