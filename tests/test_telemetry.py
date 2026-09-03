"""Tests for the OTEL instrumentation added by gm-mcp-server-664.1.

Covers the `_instrumented` decorator applied to every `@mcp.tool()` handler, the
`instrument_httpx` call site in `app_lifespan`, and the `setup_telemetry` /
`shutdown_telemetry` bracket in `main()`. Domain-instrument assertions use an
in-memory metric reader instead of a real OTLP exporter.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


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
