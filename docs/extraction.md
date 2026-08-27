# Source extraction

`mcp-server` was extracted without modifying the original `SimplicityGuy/discogsography` repository.

```bash
git clone --no-local --single-branch --no-tags \
  --branch wt/bead/issue/discogsography-2kpm.22 \
  /Users/Robert/workspaces/github/SimplicityGuy/discogsography mcp-server
git filter-repo --force \
  --path mcp-server/ --path-rename mcp-server/: \
  --path tests/mcp-server/ --path-rename tests/mcp-server/:tests/ \
  --path LICENSE \
  --path docs/superpowers/plans/2026-03-14-mcp-server.md \
  --path docs/superpowers/specs/2026-03-25-natural-language-graph-queries-design.md \
  --path docs/superpowers/specs/2026-04-14-ask-mode-integration-design.md \
  --path docs/architecture.md \
  --path docs/configuration.md \
  --path docs/development.md
```

The filtered source branch contains 106 retained commits before the standalone establishment commit. `source-main-filtered` preserves the filtered pre-migration tip locally for audit. Current code is MIT-licensed by owner decision; historical license states remain visible in retained history.
