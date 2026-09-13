# MCP server configuration

The server has one application setting:

| Setting | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8004` | Base URL for the GrooveMap Catalog API |

The server does not currently read `API_TOKEN`, `API_TOKEN_FILE`, or any other credential
variable, and it does not add an authorization header to Catalog API requests. Keep the
server and its Catalog API connection inside a trusted deployment boundary until an
authenticated upstream contract is implemented. See [transports and security](security.md).

## Transport selection

| CLI form | Result |
| --- | --- |
| no transport flag | `stdio` |
| `--transport streamable-http`, `-t streamable-http`, or `--transport=streamable-http` | Streamable HTTP |
| a missing or unsupported transport value | Falls back to `stdio` |

The adapter passes only the selected transport to the pinned MCP SDK. Consequently,
Streamable HTTP uses the SDK defaults: `127.0.0.1:8000`, path `/mcp`, stateful sessions, and
streaming responses. There is no application environment variable or CLI flag for the bind
host, port, or path.

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
| `OTEL_PROPAGATORS` | Propagator selection | W3C TraceContext plus baggage |
| `OTEL_SDK_DISABLED` | Standard SDK kill switch | `false` |
| `OTEL_SERVICE_NAME` | `service.name`, overriding the `mcp-server` default | `mcp-server` |
| `OTEL_RESOURCE_ATTRIBUTES` | Extra resource attributes, for example `service.namespace=groovemap,deployment.environment.name=dev` | empty |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | HTTP semantic-convention selection | `http` |

With `OTEL_EXPORTER_OTLP_ENDPOINT` unset (the default for local development), the server
installs no-op meter and tracer providers and starts and behaves exactly as it would without
the `otel` extra — telemetry never fails startup or blocks a tool call. The two signals are
independent: `OTEL_TRACES_EXPORTER=none` with an endpoint set keeps metrics flowing and creates
no spans at all.

Both signals are pushed over OTLP/HTTP-protobuf, never scraped: this server does not expose a
`/metrics` endpoint.

### Metrics

The lifespan-owned Catalog API client used by `catalog_api.api_get`/`api_post` is instrumented
via `instrument_httpx`, emitting `http.client.request.duration`. Every registered tool handler
additionally records `groovemap.mcp.tool.calls` (counter) and `groovemap.mcp.tool.duration`
(histogram, seconds). The counter has `tool` and `outcome` (`success` or `error`); the
histogram has only `tool`.

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
| `tools/call {tool}` | `SERVER` | MCP SDK attributes, including the method, protocol version, and tool name |
| `mcp.tool {tool}` | `INTERNAL` | `tool`, `outcome` (`success` or `error`), plus `error.type` with status `ERROR` when the handler raises |
| the Catalog API request | `CLIENT` | from `instrument_httpx`, route-templated by the instrumentation |

The MCP SDK's middleware extracts any trace context carried in MCP request metadata and opens
the server span. With no incoming context, as in an ordinary stdio session, that SDK span is
the trace root. `mcp.tool {tool}` stays current for the whole handler, which makes the Catalog
API request its child and puts `traceparent` on the outbound request. `{tool}` comes from the
closed set of registered tool names, never from an argument. A handled `{"error": ...}` result
sets `outcome=error` without failing the adapter span; a raised exception additionally sets
status `ERROR` and `error.type` without attaching its message or stack trace. Per-span call
counts and durations are derived by the collector's `spanmetrics` connector, never emitted
here.

See the
[runtime telemetry boundary](https://github.com/groovemap-music/python-libraries/blob/main/docs/runtime.md#telemetry-boundary)
for the full contract these calls rely on.

## Local examples

Use the default `stdio` transport:

```bash
API_BASE_URL=http://localhost:8004 uv run groovemap-mcp
```

Select the loopback-only Streamable HTTP listener for a local integration test:

```bash
API_BASE_URL=http://localhost:8004 uv run groovemap-mcp --transport streamable-http
```

A hosted deployment needs a separately reviewed way to provide a non-loopback bind address
in addition to ingress and network controls; this adapter does not expose one today.

The [`deployment` configuration guide](https://github.com/groovemap-music/deployment/blob/main/docs/configuration.md)
owns production values and secret injection. This repository owns only the setting consumed
by the MCP adapter.
