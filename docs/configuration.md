# MCP server configuration

The server has one application setting:

| Setting | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8004` | Base URL for the GrooveMap Catalog API |

The server does not currently read `API_TOKEN`, `API_TOKEN_FILE`, or any other credential
variable, and it does not add an authorization header to Catalog API requests. Keep the
server and its Catalog API connection inside a trusted deployment boundary until an
authenticated upstream contract is implemented. See [transports and security](security.md).

## Local examples

Use the default `stdio` transport:

```bash
API_BASE_URL=http://localhost:8004 uv run groovemap-mcp
```

Select Streamable HTTP only in a deployment that supplies the required ingress and network
controls:

```bash
API_BASE_URL=http://localhost:8004 uv run groovemap-mcp --transport streamable-http
```

The [`deployment` configuration guide](https://github.com/groovemap-music/deployment/blob/main/docs/configuration.md)
owns production values and secret injection. This repository owns only the setting consumed
by the MCP adapter.
