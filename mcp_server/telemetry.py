"""Tool-level metrics and tracing for the MCP registry."""

from collections.abc import Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import Any

from common import get_meter, get_tracer
from opentelemetry.trace import Status, StatusCode


ToolHandler = Callable[..., Awaitable[dict[str, Any]]]

_meter = get_meter("groovemap.mcp-server")
_tool_calls = _meter.create_counter(
    "groovemap.mcp.tool.calls",
    description="MCP tool invocations",
)
_tool_duration = _meter.create_histogram(
    "groovemap.mcp.tool.duration",
    unit="s",
    description="MCP tool call duration",
)
_tracer = get_tracer("groovemap.mcp-server")


def instrumented(tool_name: str) -> Callable[[ToolHandler], ToolHandler]:
    """Measure and trace one registered tool without changing its signature."""
    span_name = f"mcp.tool {tool_name}"

    def decorator(func: ToolHandler) -> ToolHandler:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            start = perf_counter()
            with _tracer.start_as_current_span(span_name, record_exception=False, set_status_on_exception=False) as span:
                span.set_attribute("tool", tool_name)
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    duration = perf_counter() - start
                    _tool_calls.add(1, {"tool": tool_name, "outcome": "error"})
                    _tool_duration.record(duration, {"tool": tool_name})
                    span.set_attribute("outcome", "error")
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_status(Status(StatusCode.ERROR))
                    raise

                duration = perf_counter() - start
                outcome = "error" if isinstance(result, dict) and "error" in result else "success"
                _tool_calls.add(1, {"tool": tool_name, "outcome": outcome})
                _tool_duration.record(duration, {"tool": tool_name})
                span.set_attribute("outcome", outcome)
                return result

        return wrapper

    return decorator
