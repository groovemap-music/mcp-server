# MCP server configuration

The server has one application setting:

| Setting | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8004` | Base URL for the GrooveMap Catalog API |

The server does not currently read `API_TOKEN`, `API_TOKEN_FILE`, or any other credential
variable, and it does not add an authorization header to Catalog API requests. Keep the
server and its Catalog API connection inside a trusted deployment boundary until an
authenticated upstream contract is implemented. See [transports and security](security.md).

## OpenTelemetry metrics

`main()` calls `common.telemetry.setup_telemetry("mcp-server")` on startup and
`shutdown_telemetry()` before exiting, in both `stdio` and Streamable HTTP transport. Only
standard OpenTelemetry environment variables configure it — there is no GrooveMap-specific
telemetry setting:

| Variable | Meaning | Default |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector base URL, for example `http://otel-collector:4318` | unset, which disables export |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Metrics-only endpoint override | falls back to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `OTEL_METRICS_EXPORTER` | `otlp` or `none` | `otlp` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Push interval in milliseconds | SDK default |
| `OTEL_SERVICE_NAME` | `service.name`, overriding the `mcp-server` default | `mcp-server` |
| `OTEL_RESOURCE_ATTRIBUTES` | Extra resource attributes, for example `service.namespace=groovemap,deployment.environment.name=dev` | empty |

With `OTEL_EXPORTER_OTLP_ENDPOINT` unset (the default for local development), the server
installs a no-op `MeterProvider` and starts and behaves exactly as it would without the
`otel` extra — telemetry never fails startup or blocks a tool call.

Metrics are pushed over OTLP/HTTP-protobuf, never scraped: this server does not expose a
`/metrics` endpoint. `_api_get`/`_api_post` (the Catalog API client used by every tool) are
instrumented via `instrument_httpx`, emitting `http.client.request.duration`. Every
`@mcp.tool()` handler additionally records `groovemap.mcp.tool.calls` (counter) and
`groovemap.mcp.tool.duration` (histogram, seconds), both attributed with `tool` (the tool
name) and, for the counter, `outcome` (`success` or `error`). See the
[runtime telemetry boundary](https://github.com/groovemap-music/python-libraries/blob/main/docs/runtime.md#telemetry-boundary)
for the full contract these calls rely on.

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
