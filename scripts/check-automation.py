"""Validate the repository-owned CI, release, and container contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_REVISION = "7db8b4c535c79329e3821e32177932b4f9059253"
PRIVATE_LIBRARY_REVISION = "28fa329702bc76896cc54ab8d05ec5b1bd3d929e"


def require(text: str, *fragments: str) -> None:
    for fragment in fragments:
        assert fragment in text, f"required automation contract fragment is absent: {fragment}"


workflow_directory = ROOT / ".github" / "workflows"
workflow_files = sorted(path.name for path in workflow_directory.iterdir() if path.suffix in {".yml", ".yaml"})
assert workflow_files == ["ci.yml", "release.yml"], workflow_files

ci = (workflow_directory / "ci.yml").read_text(encoding="utf-8")
release = (workflow_directory / "release.yml").read_text(encoding="utf-8")
dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

require(
    ci,
    "  pull_request:\n",
    "  push:\n    branches: [main]\n",
    "  schedule:\n",
    "  workflow_dispatch:\n",
    f"uses: groovemap-music/automation/.github/workflows/reusable-ci.yml@{AUTOMATION_REVISION}",
    "language: python",
    "check-command: just ci-check",
    "coverage-command: just coverage",
    "audit-command: just audit",
    "license-command: just license-check",
    "secret-scan-command: just security",
    "package-command: just build",
    "install-command: just install-check",
    "image-command: just image",
    "upload-codecov: true",
    "requires-private-library: true",
    "private-library-client-id: ${{ vars.GROOVEMAP_CI_APP_CLIENT_ID }}",
    f"private-library-revision: {PRIVATE_LIBRARY_REVISION}",
    "PRIVATE_LIBRARY_PRIVATE_KEY: ${{ secrets.GROOVEMAP_CI_APP_PRIVATE_KEY }}",
    "CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}",
)

require(
    release,
    '  push:\n    tags: ["v*"]\n',
    "  attestations: write",
    "  id-token: write",
    "  packages: write",
    f"uses: groovemap-music/automation/.github/workflows/reusable-release.yml@{AUTOMATION_REVISION}",
    "repository-name: mcp-server",
    "release-command: just release-dry-run",
    "publish-image: true",
    "requires-private-library: true",
    "private-library-client-id: ${{ vars.GROOVEMAP_CI_APP_CLIENT_ID }}",
    f"private-library-revision: {PRIVATE_LIBRARY_REVISION}",
    "prepare-image-command: just prepare-image",
    "PRIVATE_LIBRARY_PRIVATE_KEY: ${{ secrets.GROOVEMAP_CI_APP_PRIVATE_KEY }}",
)

for workflow in (ci, release):
    folded = workflow.casefold()
    for forbidden in ("@main", "github.actor", "dependabot[bot]", "renovate", "claude"):
        assert forbidden not in folded, f"forbidden workflow exception or mutable reference: {forbidden}"

require(dependabot, "package-ecosystem: github-actions", "package-ecosystem: uv", "labels: [dependencies, github-actions]")
assert "renovate" not in dependabot.casefold()

require(
    dockerfile,
    'org.opencontainers.image.title="mcp-server"',
    'org.opencontainers.image.source="https://github.com/groovemap-music/mcp-server"',
    'org.opencontainers.image.licenses="MIT"',
    "USER 1000:1000",
    'ENTRYPOINT ["/app/.venv/bin/groovemap-mcp"]',
    'CMD ["--transport", "streamable-http"]',
)
assert ("discogs" + "ography") not in dockerfile.casefold()

print("CI, release, Dependabot, and mcp-server image contracts are valid.")
