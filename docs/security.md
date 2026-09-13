# Transports and security

The server supports the MCP SDK's `stdio` and `streamable-http` transports.

## `stdio`

`stdio` is the default. An MCP client launches `groovemap-mcp`, communicates over the
child process's standard streams, and controls who can invoke tools. This is the preferred
local-development and desktop-client boundary.

## Streamable HTTP

`groovemap-mcp --transport streamable-http` starts the pinned SDK's stateful Streamable HTTP
transport at `http://127.0.0.1:8000/mcp`. The adapter passes no bind options and exposes no
host, port, or path environment variables. The image declares port 8000 and selects this
transport by default, but the SDK's loopback bind means the image alone is not a remotely
reachable hosted endpoint.

This repository does not configure ingress authentication, TLS termination, or network
policy. Do not expose the listener directly to an untrusted network.

An approved hosted deployment must provide those controls and a reviewed non-loopback serving
arrangement. That design is owned by the
[`deployment`](https://github.com/groovemap-music/deployment) repository; changing this
adapter's bind contract requires an explicit runtime change.

## Catalog API authentication boundary

The current adapter sends no bearer token or other authorization header to `catalog-api`.
`API_BASE_URL` therefore must identify a Catalog API endpoint reachable only within the
trusted local or deployment boundary. The promoted MCP v1 routes are public, no-token
Catalog API routes. `catalog-api` owns route authentication and authorization where
implemented, plus rate limiting and data-access policy; `mcp-server` must not bypass those
controls with direct database access.

Secrets, private endpoints, generated client configuration, and machine-specific paths
must not be committed. Production values and secret injection belong to `deployment`.

See [configuration](configuration.md), [architecture](architecture.md), and the public
[GrooveMap logging emoji convention](https://github.com/groovemap-music/.github/blob/main/docs/emoji-guide.md).
