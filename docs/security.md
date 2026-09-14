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

The catalog routes are public, no-token Catalog API routes; the three delegated tools carry
a scoped app token supplied by configuration; erasure and export are never exposed as tools.
`API_BASE_URL` must therefore still identify a Catalog API endpoint reachable only within the
trusted local or deployment boundary, because the catalog half of the surface is protected by
that boundary and nothing else.

The delegated half is `record_recommendation_outcome`, `get_consent`, and `set_consent`. They
act for a collector, so they need a credential, and `GROOVEMAP_CATALOG_APP_TOKEN` is the only
way to supply one: `app_lifespan` reads it once at startup, no tool accepts it as an argument,
and no tool can reach the environment. With the variable unset those three tools return a
`delegation not configured` error without making a request, which is the safe default — an
operator opts a deployment into delegation rather than out of it. The bearer header goes only
to the delegated routes, and the token is never logged, never echoed in an error, and never
returned to the agent.

Erasure and export are deliberately absent from the tool surface even though the promoted
contract carries their routes. Destroying an account's data or exporting all of it is a
session-only right that a person exercises for themselves; a delegated credential must not be
able to do either, so no tool offers it.

`catalog-api` owns route authentication and authorization, the scopes the app token is
granted, rate limiting, and data-access policy; `mcp-server` must not bypass those controls
with direct database access.

Secrets, private endpoints, generated client configuration, and machine-specific paths
must not be committed. Production values and secret injection belong to `deployment`.

See [configuration](configuration.md), [architecture](architecture.md), and the public
[GrooveMap logging emoji convention](https://github.com/groovemap-music/.github/blob/main/docs/emoji-guide.md).
