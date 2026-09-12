"""Bind tool-routing policy to an MCP server instance."""

from mcp.server import MCPServer  # noqa: TC002 -- keeping this tiny boundary concrete is clearer

from mcp_server.telemetry import ToolHandler, instrumented
from mcp_server.tool_routing import TOOL_HANDLERS


def register_tools(server: MCPServer) -> tuple[ToolHandler, ...]:
    """Register all tools in their stable public order and return the wrappers."""
    return tuple(server.tool(name=handler.__name__)(instrumented(handler.__name__)(handler)) for handler in TOOL_HANDLERS)
