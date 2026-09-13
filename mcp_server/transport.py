"""CLI transport selection and dispatch."""

from collections.abc import Sequence  # noqa: TC003 -- keeps the parser's accepted input explicit
from typing import Literal

from mcp.server import MCPServer  # noqa: TC002 -- run dispatch is intentionally concrete


Transport = Literal["stdio", "streamable-http"]


def select_transport(arguments: Sequence[str]) -> Transport:
    """Parse the established transport flags, falling back to stdio."""
    selected = "stdio"
    for index, argument in enumerate(arguments):
        if argument in ("--transport", "-t") and index < len(arguments) - 1:
            selected = arguments[index + 1]
            break
        if argument.startswith("--transport="):
            selected = argument.split("=", 1)[1]
            break
    if selected == "streamable-http":
        return "streamable-http"
    return "stdio"


def run_transport(server: MCPServer, transport: Transport) -> None:
    """Call the MCP SDK overload matching the validated transport."""
    if transport == "streamable-http":
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")
