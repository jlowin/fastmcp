from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer as SDKServer

    from fastmcp.client.transports.base import ClientTransport as ClientTransport
    from fastmcp.client.transports.base import ClientTransportT as ClientTransportT
    from fastmcp.client.transports.base import SessionKwargs as SessionKwargs
    from fastmcp.client.transports.config import (
        MCPConfigTransport as MCPConfigTransport,
    )
    from fastmcp.client.transports.http import (
        StreamableHttpTransport as StreamableHttpTransport,
    )
    from fastmcp.client.transports.inference import infer_transport as infer_transport
    from fastmcp.client.transports.memory import FastMCPTransport as FastMCPTransport
    from fastmcp.client.transports.sse import SSETransport as SSETransport
    from fastmcp.client.transports.stdio import (
        FastMCPStdioTransport as FastMCPStdioTransport,
    )
    from fastmcp.client.transports.stdio import NodeStdioTransport as NodeStdioTransport
    from fastmcp.client.transports.stdio import NpxStdioTransport as NpxStdioTransport
    from fastmcp.client.transports.stdio import (
        PythonStdioTransport as PythonStdioTransport,
    )
    from fastmcp.client.transports.stdio import StdioTransport as StdioTransport
    from fastmcp.client.transports.stdio import UvStdioTransport as UvStdioTransport
    from fastmcp.client.transports.stdio import UvxStdioTransport as UvxStdioTransport

__all__ = [
    "ClientTransport",
    "FastMCPStdioTransport",
    "FastMCPTransport",
    "NodeStdioTransport",
    "NpxStdioTransport",
    "PythonStdioTransport",
    "SSETransport",
    "StdioTransport",
    "StreamableHttpTransport",
    "UvStdioTransport",
    "UvxStdioTransport",
    "infer_transport",
]

_LAZY_IMPORTS = {
    "ClientTransport": ("fastmcp.client.transports.base", "ClientTransport"),
    "ClientTransportT": ("fastmcp.client.transports.base", "ClientTransportT"),
    "FastMCPStdioTransport": (
        "fastmcp.client.transports.stdio",
        "FastMCPStdioTransport",
    ),
    "FastMCPTransport": ("fastmcp.client.transports.memory", "FastMCPTransport"),
    "MCPConfigTransport": (
        "fastmcp.client.transports.config",
        "MCPConfigTransport",
    ),
    "NodeStdioTransport": (
        "fastmcp.client.transports.stdio",
        "NodeStdioTransport",
    ),
    "NpxStdioTransport": (
        "fastmcp.client.transports.stdio",
        "NpxStdioTransport",
    ),
    "PythonStdioTransport": (
        "fastmcp.client.transports.stdio",
        "PythonStdioTransport",
    ),
    "SDKServer": ("mcp.server.mcpserver", "MCPServer"),
    "SSETransport": ("fastmcp.client.transports.sse", "SSETransport"),
    "SessionKwargs": ("fastmcp.client.transports.base", "SessionKwargs"),
    "StdioTransport": ("fastmcp.client.transports.stdio", "StdioTransport"),
    "StreamableHttpTransport": (
        "fastmcp.client.transports.http",
        "StreamableHttpTransport",
    ),
    "UvStdioTransport": ("fastmcp.client.transports.stdio", "UvStdioTransport"),
    "UvxStdioTransport": ("fastmcp.client.transports.stdio", "UvxStdioTransport"),
    "infer_transport": ("fastmcp.client.transports.inference", "infer_transport"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
