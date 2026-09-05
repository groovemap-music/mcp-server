"""Tests for the OTEL instrumentation added by gm-mcp-server-664.1 and gm-mcp-server-qv3.1.

Covers the `_instrumented` decorator applied to every `@mcp.tool()` handler — both the
`groovemap.mcp.tool.*` metrics and the `mcp.tool {tool}` root span it opens — the
`instrument_httpx` and `start_event_loop_monitor` call sites in `app_lifespan`, and the
`setup_telemetry` / `shutdown_telemetry` bracket in `main()`. Domain-signal assertions use
the in-memory metric reader and span exporter instead of a real OTLP exporter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from common import telemetry
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode


if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk.trace import ReadableSpan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def metric_reader(monkeypatch: pytest.MonkeyPatch) -> InMemoryMetricReader:
    """Point mcp_server.server's module-level instruments at a fresh in-memory reader.

    Builds a dedicated SDK MeterProvider per test instead of touching the process-wide
    OpenTelemetry provider, so tests stay isolated from each other and from whatever
    common.telemetry.setup_telemetry() has (or has not) installed globally.
    """
    import mcp_server.server as server

    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("groovemap.mcp-server")
    tool_calls = meter.create_counter("groovemap.mcp.tool.calls", description="MCP tool invocations")
    tool_duration = meter.create_histogram("groovemap.mcp.tool.duration", unit="s", description="MCP tool call duration")
    monkeypatch.setattr(server, "_tool_calls", tool_calls)
    monkeypatch.setattr(server, "_tool_duration", tool_duration)
    return reader


class SpanCollector:
    """An in-memory tracer provider whose finished spans can be read back by name."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))

    def spans(self) -> tuple[ReadableSpan, ...]:
        return self.exporter.get_finished_spans()

    def named(self, name: str) -> list[ReadableSpan]:
        return [span for span in self.spans() if span.name == name]

    def only(self, name: str) -> ReadableSpan:
        matching = self.named(name)
        assert len(matching) == 1, f"expected exactly one {name!r} span, saw {[span.name for span in self.spans()]}"
        return matching[0]

    def of_kind(self, kind: SpanKind) -> list[ReadableSpan]:
        return [span for span in self.spans() if span.kind is kind]


@pytest.fixture()
def spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[SpanCollector]:
    """Record every span the server opens into an in-memory exporter.

    Binds both ends the same way the runtime does: `mcp_server.server._tracer` is the handle
    the tool decorator opens spans through, and `common.telemetry._tracer_provider` is what
    `instrument_httpx` reads, so the Catalog API client span lands in the same provider as
    the tool span it should be a child of.
    """
    import mcp_server.server as server

    collector = SpanCollector()
    monkeypatch.setattr(telemetry, "_tracer_provider", collector.provider)
    monkeypatch.setattr(server, "_tracer", collector.provider.get_tracer("groovemap.mcp-server"))
    yield collector
    monkeypatch.setattr(telemetry, "_tracer_provider", None)


@pytest.fixture()
def app_ctx() -> Any:
    """Create an AppContext with a mocked httpx client (mirrors tests/test_server.py)."""
    from mcp_server.server import AppContext

    client = MagicMock(spec=httpx.AsyncClient)
    return AppContext(client=client, base_url="http://test-api:8004")


@pytest.fixture()
def mock_context(app_ctx: Any) -> Any:
    """Create a mock MCP Context whose lifespan_context is our AppContext."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    return ctx


def _mock_response(json_data: dict[str, Any], status_code: int = 200) -> httpx.Response:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    return resp


def _data_points(reader: InMemoryMetricReader, metric_name: str) -> list[Any]:
    """Flatten every data point recorded for one metric name across all scopes."""
    points: list[Any] = []
    data = reader.get_metrics_data()
    if data is None:
        return points
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == metric_name:
                    points.extend(metric.data.data_points)
    return points


# ---------------------------------------------------------------------------
# _instrumented decorator: unit-level, independent of any real tool
# ---------------------------------------------------------------------------


class TestInstrumentedDecorator:
    @pytest.mark.asyncio
    async def test_records_success_outcome(self, metric_reader: InMemoryMetricReader) -> None:
        from mcp_server.server import _instrumented

        @_instrumented("fake_tool")
        async def handler() -> dict[str, Any]:
            return {"ok": True}

        result = await handler()
        assert result == {"ok": True}

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert len(calls) == 1
        assert dict(calls[0].attributes) == {"tool": "fake_tool", "outcome": "success"}

        durations = _data_points(metric_reader, "groovemap.mcp.tool.duration")
        assert len(durations) == 1
        assert dict(durations[0].attributes) == {"tool": "fake_tool"}
        assert durations[0].count == 1
        assert durations[0].sum >= 0

    @pytest.mark.asyncio
    async def test_records_error_outcome_for_error_dict(self, metric_reader: InMemoryMetricReader) -> None:
        from mcp_server.server import _instrumented

        @_instrumented("fake_tool")
        async def handler() -> dict[str, Any]:
            return {"error": "boom"}

        result = await handler()
        assert result == {"error": "boom"}

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert len(calls) == 1
        assert dict(calls[0].attributes) == {"tool": "fake_tool", "outcome": "error"}

    @pytest.mark.asyncio
    async def test_records_error_outcome_and_reraises_on_exception(self, metric_reader: InMemoryMetricReader) -> None:
        from mcp_server.server import _instrumented

        @_instrumented("fake_tool")
        async def handler() -> dict[str, Any]:
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            await handler()

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert len(calls) == 1
        assert dict(calls[0].attributes) == {"tool": "fake_tool", "outcome": "error"}

        durations = _data_points(metric_reader, "groovemap.mcp.tool.duration")
        assert len(durations) == 1
        assert dict(durations[0].attributes) == {"tool": "fake_tool"}

    def test_preserves_wrapped_function_metadata(self) -> None:
        """mcp.tool() relies on the wrapped signature/docstring to build its JSON schema."""
        from mcp_server.server import _instrumented

        async def handler(x: int) -> dict[str, Any]:
            """Docstring the MCP SDK reads."""
            return {"x": x}

        wrapped = _instrumented("fake_tool")(handler)
        assert wrapped.__name__ == "handler"
        assert wrapped.__doc__ == "Docstring the MCP SDK reads."
        assert wrapped.__wrapped__ is handler


# ---------------------------------------------------------------------------
# Real tool handlers, on the main (success) path
# ---------------------------------------------------------------------------


class TestToolMetricsOnMainPath:
    @pytest.mark.asyncio
    async def test_search_records_success(self, metric_reader: InMemoryMetricReader, mock_context: Any, app_ctx: Any) -> None:
        from mcp_server.server import search

        fake_response = {
            "query": "miles",
            "total": 1,
            "facets": {"type": {"artist": 1}, "genre": {}, "decade": {}},
            "results": [],
            "pagination": {"limit": 20, "offset": 0, "has_more": False},
        }
        app_ctx.client.get = AsyncMock(return_value=_mock_response(fake_response))

        result = await search(query="miles", ctx=mock_context)
        assert result["total"] == 1

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert len(calls) == 1
        assert dict(calls[0].attributes) == {"tool": "search", "outcome": "success"}

    @pytest.mark.asyncio
    async def test_search_invalid_type_records_error_without_calling_api(
        self, metric_reader: InMemoryMetricReader, mock_context: Any, app_ctx: Any
    ) -> None:
        from mcp_server.server import search

        result = await search(query="test", types="invalid", ctx=mock_context)
        assert "error" in result
        app_ctx.client.get.assert_not_called()

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert len(calls) == 1
        assert dict(calls[0].attributes) == {"tool": "search", "outcome": "error"}

    @pytest.mark.asyncio
    async def test_get_graph_stats_records_success(self, metric_reader: InMemoryMetricReader, mock_context: Any, app_ctx: Any) -> None:
        from mcp_server.server import get_graph_stats

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"artists": 1}))

        result = await get_graph_stats(ctx=mock_context)
        assert result == {"artists": 1}

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert dict(calls[0].attributes) == {"tool": "get_graph_stats", "outcome": "success"}

    @pytest.mark.asyncio
    async def test_api_http_error_records_error_outcome(self, metric_reader: InMemoryMetricReader, mock_context: Any, app_ctx: Any) -> None:
        """_api_get never raises on an HTTP error — it returns {"error": ...}; outcome must reflect that."""
        from mcp_server.server import get_graph_stats

        request = httpx.Request("GET", "http://test-api:8004/api/graph/stats")
        error_response = httpx.Response(status_code=500, request=request)
        app_ctx.client.get = AsyncMock(
            return_value=MagicMock(
                spec=httpx.Response,
                status_code=500,
                raise_for_status=MagicMock(side_effect=httpx.HTTPStatusError("boom", request=request, response=error_response)),
            )
        )

        result = await get_graph_stats(ctx=mock_context)
        assert "error" in result

        calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
        assert dict(calls[0].attributes) == {"tool": "get_graph_stats", "outcome": "error"}


# ---------------------------------------------------------------------------
# app_lifespan: instrument_httpx call site
# ---------------------------------------------------------------------------


class TestAppLifespanInstrumentsHttpx:
    @pytest.mark.asyncio
    async def test_instrument_httpx_called_with_the_lifespan_client(self) -> None:
        import mcp_server.server as server

        with patch.object(server, "instrument_httpx") as mock_instrument:
            async with server.app_lifespan(MagicMock()) as ctx:
                mock_instrument.assert_called_once_with(ctx.client)


# ---------------------------------------------------------------------------
# main(): setup_telemetry / shutdown_telemetry bracket
# ---------------------------------------------------------------------------


class TestMainTelemetryLifecycle:
    def test_setup_and_shutdown_called_around_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mcp_server.server as server

        monkeypatch.setattr(server.sys, "argv", ["groovemap-mcp"])
        calls: list[str] = []
        monkeypatch.setattr(server, "setup_telemetry", lambda name: calls.append(f"setup:{name}"))
        monkeypatch.setattr(server, "shutdown_telemetry", lambda: calls.append("shutdown"))
        monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(f"run:{kwargs.get('transport')}"))

        server.main()

        assert calls == ["setup:mcp-server", "run:stdio", "shutdown"]

    def test_shutdown_still_runs_when_run_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stdio sessions can be short-lived; the last export must still flush on any exit path."""
        import mcp_server.server as server

        monkeypatch.setattr(server.sys, "argv", ["groovemap-mcp"])
        calls: list[str] = []
        monkeypatch.setattr(server, "setup_telemetry", lambda name: calls.append(f"setup:{name}"))
        monkeypatch.setattr(server, "shutdown_telemetry", lambda: calls.append("shutdown"))

        def _raise(**kwargs: Any) -> None:
            raise RuntimeError("client disconnected")

        monkeypatch.setattr(server.mcp, "run", _raise)

        with pytest.raises(RuntimeError, match="client disconnected"):
            server.main()

        assert calls == ["setup:mcp-server", "shutdown"]

    def test_streamable_http_transport_selected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mcp_server.server as server

        monkeypatch.setattr(server.sys, "argv", ["groovemap-mcp", "--transport", "streamable-http"])
        calls: list[str] = []
        monkeypatch.setattr(server, "setup_telemetry", lambda name: calls.append(f"setup:{name}"))
        monkeypatch.setattr(server, "shutdown_telemetry", lambda: calls.append("shutdown"))
        monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(f"run:{kwargs.get('transport')}"))

        server.main()

        assert calls == ["setup:mcp-server", "run:streamable-http", "shutdown"]


# ---------------------------------------------------------------------------
# Regression: OTEL_EXPORTER_OTLP_ENDPOINT unset -> behaves exactly as before
# ---------------------------------------------------------------------------


class TestOtelDisabledRegression:
    def test_main_runs_unchanged_with_endpoint_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No OTEL_* env (scrubbed by the autouse fixture): setup_telemetry must not raise,
        must not block startup, and main() must run exactly as it did before this bead.
        """
        import mcp_server.server as server

        monkeypatch.setattr(server.sys, "argv", ["groovemap-mcp"])
        monkeypatch.setattr(server.mcp, "run", MagicMock())

        server.main()  # must not raise

        server.mcp.run.assert_called_once_with(transport="stdio")

    @pytest.mark.asyncio
    async def test_tool_call_succeeds_with_endpoint_unset(self, mock_context: Any, app_ctx: Any) -> None:
        """The no-op MeterProvider swallows measurements silently; the tool result is unaffected."""
        from mcp_server.server import get_graph_stats

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"artists": 42}))

        result = await get_graph_stats(ctx=mock_context)

        assert result == {"artists": 42}

    def test_get_meter_returns_a_usable_meter_without_setup(self) -> None:
        """common.telemetry.get_meter() must hand back a working (no-op) meter before/without
        setup_telemetry, per the runtime contract — module import must never fail here.
        """
        from mcp_server.server import _meter

        counter = _meter.create_counter("groovemap.mcp.tool.calls")
        counter.add(1, {"tool": "search", "outcome": "success"})  # must not raise


# ---------------------------------------------------------------------------
# _instrumented: the `mcp.tool {tool}` root span
# ---------------------------------------------------------------------------


class TestToolSpans:
    @pytest.mark.asyncio
    async def test_tool_call_opens_an_mcp_tool_root_span(self, spans: SpanCollector, mock_context: Any, app_ctx: Any) -> None:
        """The span name is the low-cardinality `mcp.tool {tool}`, and it starts a new trace."""
        from mcp_server.server import get_graph_stats

        app_ctx.client.get = AsyncMock(return_value=_mock_response({"artists": 1}))

        await get_graph_stats(ctx=mock_context)

        span = spans.only("mcp.tool get_graph_stats")
        assert span.parent is None
        assert span.kind is SpanKind.INTERNAL
        assert dict(span.attributes or {}) == {"tool": "get_graph_stats", "outcome": "success"}
        assert span.status.status_code is not StatusCode.ERROR

    @pytest.mark.asyncio
    async def test_error_dict_result_records_outcome_error_without_failing_the_span(
        self, spans: SpanCollector, mock_context: Any, app_ctx: Any
    ) -> None:
        """An {"error": ...} body is a handled MCP response, so only `outcome` reports it."""
        from mcp_server.server import search

        result = await search(query="test", types="invalid", ctx=mock_context)
        assert "error" in result
        app_ctx.client.get.assert_not_called()

        span = spans.only("mcp.tool search")
        assert dict(span.attributes or {}) == {"tool": "search", "outcome": "error"}
        assert span.status.status_code is not StatusCode.ERROR

    @pytest.mark.asyncio
    async def test_raised_exception_sets_error_status_and_error_type_only(self, spans: SpanCollector) -> None:
        """Span conventions: status ERROR with error.type, never a message or a stack trace."""
        from mcp_server.server import _instrumented

        @_instrumented("fake_tool")
        async def handler() -> dict[str, Any]:
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            await handler()

        span = spans.only("mcp.tool fake_tool")
        assert dict(span.attributes or {}) == {"tool": "fake_tool", "outcome": "error", "error.type": "ValueError"}
        assert span.status.status_code is StatusCode.ERROR
        assert span.status.description is None
        assert span.events == ()

    @pytest.mark.asyncio
    async def test_catalog_api_request_is_a_child_span_carrying_traceparent(self, spans: SpanCollector, mock_context: Any, app_ctx: Any) -> None:
        """The outbound Catalog API call continues the tool's trace into catalog-api.

        Uses a real httpx.AsyncClient over a MockTransport so the httpx instrumentation the
        server installs through instrument_httpx() actually runs: it is what opens the CLIENT
        span and writes `traceparent` onto the request.
        """
        import mcp_server.server as server
        from mcp_server.server import get_graph_stats

        seen: list[httpx.Headers] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers)
            return httpx.Response(200, json={"artists": 1})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=1.0)
        assert server.instrument_httpx(client) is True
        try:
            app_ctx.client = client
            async with client:
                result = await get_graph_stats(ctx=mock_context)
        finally:
            HTTPXClientInstrumentor.uninstrument_client(client)

        assert result == {"artists": 1}

        tool_span = spans.only("mcp.tool get_graph_stats")
        client_spans = spans.of_kind(SpanKind.CLIENT)
        assert len(client_spans) == 1
        client_span = client_spans[0]

        assert client_span.parent is not None
        assert client_span.parent.span_id == tool_span.context.span_id
        assert client_span.context.trace_id == tool_span.context.trace_id

        assert len(seen) == 1
        traceparent = seen[0]["traceparent"]
        assert format(tool_span.context.trace_id, "032x") in traceparent


# ---------------------------------------------------------------------------
# app_lifespan: the event-loop monitor
# ---------------------------------------------------------------------------


class TestAppLifespanStartsEventLoopMonitor:
    @pytest.mark.asyncio
    async def test_monitor_is_started_from_the_transport_loop_after_instrumentation(self) -> None:
        """mcp.run() owns the loop, so the lifespan is the first place inside it that can sample."""
        import mcp_server.server as server

        order: list[str] = []
        with (
            patch.object(server, "instrument_httpx", side_effect=lambda _client: order.append("instrument_httpx")),
            patch.object(server, "start_event_loop_monitor", side_effect=lambda: order.append("start_event_loop_monitor")) as monitor,
        ):
            async with server.app_lifespan(MagicMock()):
                pass

        monitor.assert_called_once_with()
        assert order == ["instrument_httpx", "start_event_loop_monitor"]

    @pytest.mark.asyncio
    async def test_monitor_is_a_no_op_without_a_configured_provider(self) -> None:
        """With telemetry unconfigured the library returns None; the lifespan must not care."""
        import mcp_server.server as server

        async with server.app_lifespan(MagicMock()) as ctx:
            assert ctx.base_url


# ---------------------------------------------------------------------------
# main(): the stdio exit path force-flushes BOTH providers
# ---------------------------------------------------------------------------


class TestShutdownFlushesBothProviders:
    def test_exit_force_flushes_and_shuts_down_traces_and_metrics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stdio session can end at any moment; neither signal may be left in a buffer."""
        import mcp_server.server as server

        meter_provider = MagicMock()
        tracer_provider = MagicMock()
        monkeypatch.setattr(telemetry, "_sdk_provider", meter_provider)
        monkeypatch.setattr(telemetry, "_sdk_tracer_provider", tracer_provider)
        monkeypatch.setattr(server.sys, "argv", ["groovemap-mcp"])
        monkeypatch.setattr(server, "setup_telemetry", lambda _name: None)
        monkeypatch.setattr(server.mcp, "run", MagicMock())

        server.main()

        tracer_provider.force_flush.assert_called_once()
        tracer_provider.shutdown.assert_called_once()
        meter_provider.force_flush.assert_called_once()
        meter_provider.shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# Endpoint set, traces off: metrics flow and nothing can emit a span
# ---------------------------------------------------------------------------


class TestTracesDisabledWithEndpointSet:
    @pytest.mark.asyncio
    async def test_metrics_flow_and_no_span_is_recorded(
        self, monkeypatch: pytest.MonkeyPatch, metric_reader: InMemoryMetricReader, mock_context: Any, app_ctx: Any
    ) -> None:
        """OTEL_TRACES_EXPORTER=none turns tracing off on its own; metrics keep exporting.

        Port 1 is never listening, so the OTLP exporter fails fast instead of holding the
        shutdown flush open; nothing in this test depends on an export succeeding.
        """
        import mcp_server.server as server
        from mcp_server.server import get_graph_stats

        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
        monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "600000")

        telemetry.shutdown_telemetry(timeout_s=0.1)
        try:
            provider = telemetry.setup_telemetry("mcp-server")

            # Metrics half: a real SDK provider is installed, so measurements are exported.
            assert isinstance(provider, MeterProvider)
            assert telemetry._sdk_provider is not None

            # Tracing half: no SDK tracer provider exists at all, so no span can reach an
            # exporter, and the span the tool decorator opens is not even recorded.
            assert telemetry._sdk_tracer_provider is None
            monkeypatch.setattr(server, "_tracer", server.get_tracer("groovemap.mcp-server"))
            with server._tracer.start_as_current_span("mcp.tool probe") as probe:
                assert probe.is_recording() is False

            app_ctx.client.get = AsyncMock(return_value=_mock_response({"artists": 7}))
            assert await get_graph_stats(ctx=mock_context) == {"artists": 7}

            calls = _data_points(metric_reader, "groovemap.mcp.tool.calls")
            assert dict(calls[0].attributes) == {"tool": "get_graph_stats", "outcome": "success"}
        finally:
            telemetry.shutdown_telemetry(timeout_s=0.1)
