# GrooveMap MCP server

Model Context Protocol integration that exposes GrooveMap to AI assistants through the separately deployed `catalog-api`. It has no direct database access.

This repository is licensed under the [MIT License](LICENSE).

## Tools

| Tool | Purpose |
| --- | --- |
| `search` | Search artists, labels, masters, and releases |
| `get_artist_details` | Read an artist and its catalog relationships |
| `get_label_details` | Read a label and release count |
| `get_release_details` | Read release metadata |
| `get_genre_details` / `get_style_details` | Read taxonomy details |
| `find_path` | Find a shortest path between graph entities |
| `get_trends` | Read an entity's release timeline |
| `get_graph_stats` | Read graph-wide entity counts |
| `get_collaborators` | Read an artist collaboration network |
| `get_genre_tree` | Read the genre/style hierarchy |
| `nlq_query` | Ask a natural-language graph question |

## Development

```bash
mise install
just setup
just check
```

The stable repository interface is:

- `just setup` — install the locked environment.
- `just check` — run formatting, typing, tests, protocol/contract checks, builds, license checks, and a Commitizen preview.
- `just test` — run the focused MCP adapter suite with coverage.
- `just protocol-check` — verify the exported MCP tool surface and Catalog API compatibility.
- `just build` — build wheel and source distribution.
- `just release-dry-run` — generate checksums, SBOM, notices, and provenance without publishing.
- `just bump-preview` — preview the next Conventional Commits version without changing files.

`groovemap-agent-tools` is resolved from immutable `python-libraries` commit `28fa329702bc76896cc54ab8d05ec5b1bd3d929e`. Local operators use their existing Git credentials; no token is stored in this repository.

## Run

After installation:

```bash
API_BASE_URL=http://localhost:8004 groovemap-mcp
groovemap-mcp --transport streamable-http
```

The default transport is `stdio`. `streamable-http` is available for an explicitly designed hosted deployment.

Example local client configuration:

```json
{
  "mcpServers": {
    "groovemap": {
      "command": "groovemap-mcp",
      "env": {
        "API_BASE_URL": "http://localhost:8004"
      }
    }
  }
}
```

Do not commit generated client configuration when it contains credentials or machine-specific paths.

## Boundaries and releases

The MCP server consumes a promoted v1 Catalog API route contract and the versioned framework-neutral `groovemap-agent-tools` package. It does not import API implementation modules. Hosted release automation remains disabled until a short-lived GitHub App installation token can read the private library repository and an approved package publishing identity exists.

See [docs/extraction.md](docs/extraction.md) for retained-history provenance.
