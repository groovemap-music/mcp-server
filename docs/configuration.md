# MCP server configuration

The default transport is local `stdio`. Use streamable HTTP only for a deliberately
designed hosted deployment.

| Setting | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8004` | Catalog API origin |
| `API_TOKEN` / `API_TOKEN_FILE` | unset | Catalog API bearer credential |
| `LOG_LEVEL` | `INFO` | Structured logging threshold |

`*_FILE` values are preferred when deployment supplies Docker secrets. Never place
credentials in command arguments, committed client configuration, dependency URLs, or
workflow files.

Local examples:

```bash
API_BASE_URL=http://localhost:8004 groovemap-mcp
API_BASE_URL=http://localhost:8004 groovemap-mcp --transport streamable-http
```

The deployment repository owns production values and secret injection. See its
[configuration guide](https://github.com/groovemap-music/deployment/blob/main/docs/configuration.md)
and this repository's [documentation index](README.md).
