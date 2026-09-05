# MCP server configuration

The server has one application setting:

| Setting | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8004` | Base URL for the GrooveMap Catalog API |

The server does not currently read `API_TOKEN`, `API_TOKEN_FILE`, or any other credential
variable, and it does not add an authorization header to Catalog API requests. Keep the
server and its Catalog API connection inside a trusted deployment boundary until an
authenticated upstream contract is implemented. See [transports and security](security.md).

## OpenTelemetry metrics and traces

`main()` calls `common.telemetry.setup_telemetry("mcp-server")` on startup and
`shutdown_telemetry()` before exiting, in both `stdio` and Streamable HTTP transport. One call
installs both a `MeterProvider` and a `TracerProvider`, and the matching shutdown force-flushes
and shuts down both, so a stdio session that ends the moment its client disconnects still
exports its last metrics and its last spans. Only standard OpenTelemetry environment variables
configure it — there is no GrooveMap-specific telemetry setting:

| Variable | Meaning | Default |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector base URL, for example `http://otel-collector:4318` | unset, which disables export |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Metrics-only endpoint override | falls back to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `OTEL_METRICS_EXPORTER` | `otlp` or `none` | `otlp` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Push interval in milliseconds | SDK default |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Traces-only endpoint override | falls back to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `OTEL_TRACES_EXPORTER` | `otlp` or `none` | `otlp` |
| `OTEL_TRACES_SAMPLER` | Sampler name the SDK understands | `parentbased_traceidratio` |
| `OTEL_TRACES_SAMPLER_ARG` | Sampling ratio for the ratio samplers | `1.0` |
| `OTEL_SERVICE_NAME` | `service.name`, overriding the `mcp-server` default | `mcp-server` |
| `OTEL_RESOURCE_ATTRIBUTES` | Extra resource attributes, for example `service.namespace=groovemap,deployment.environment.name=dev` | empty |

With `OTEL_EXPORTER_OTLP_ENDPOINT` unset (the default for local development), the server
installs no-op meter and tracer providers and starts and behaves exactly as it would without
the `otel` extra — telemetry never fails startup or blocks a tool call. The two signals are
independent: `OTEL_TRACES_EXPORTER=none` with an endpoint set keeps metrics flowing and creates
no spans at all.

Both signals are pushed over OTLP/HTTP-protobuf, never scraped: this server does not expose a
`/metrics` endpoint.

### Metrics

`_api_get`/`_api_post` (the Catalog API client used by every tool) are instrumented via
`instrument_httpx`, emitting `http.client.request.duration`. Every `@mcp.tool()` handler
additionally records `groovemap.mcp.tool.calls` (counter) and `groovemap.mcp.tool.duration`
(histogram, seconds), both attributed with `tool` (the tool name) and, for the counter,
`outcome` (`success` or `error`).

`setup_telemetry` also installs the process view — `process.cpu.time`,
`process.cpu.utilization`, `process.memory.usage`, `process.memory.virtual`,
`process.thread.count`, `process.open_file_descriptor.count`, `process.context_switches`, and
the CPython garbage-collection counter — with no code in this repository. Alongside it,
`app_lifespan` starts `start_event_loop_monitor()`, which samples
`groovemap.runtime.event_loop.lag` (histogram, seconds) once a second. The transport owns the
loop: `mcp.run()` creates it and the lifespan is the first code in this process to run inside
it, so that is where the sampler is started, in both `stdio` and Streamable HTTP transport.

### Spans

| Span | Kind | Attributes |
| --- | --- | --- |
| `mcp.tool {tool}` | `INTERNAL` | `tool`, `outcome` (`success` or `error`), plus `error.type` with status `ERROR` when the handler raises |
| the Catalog API request | `CLIENT` | from `instrument_httpx`, route-templated by the instrumentation |

A stdio MCP session carries no inbound trace context, so `mcp.tool {tool}` is the root of the
trace. It stays current for the whole handler, which makes the Catalog API request its child
and puts `traceparent` on the outbound request, so one trace spans this adapter and
`catalog-api`. `{tool}` comes from the closed set of registered tool names, never from an
argument, and a span never carries an id, a query, a URL, or an exception message: a failure
sets status `ERROR` with `error.type` alone. Per-span call counts and durations are derived by
the collector's `spanmetrics` connector, never emitted here.

See the
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
