from typing import Any

from pydantic import Field

from fastmcp import FastMCP
from fastmcp.client.transports import ClientTransport, FastMCPTransport
from fastmcp.mcp_config import MCPConfig, RemoteMCPServer, StdioMCPServer
from fastmcp.tools.tool_transform import (
    ToolTransformRequest,
)
from fastmcp.utilities.types import FastMCPBaseModel


class WrappedMCPServerMixin(FastMCPBaseModel):
    """A mixin that enables wrapping an MCP Server (Or a FastMCP Agents Server) with tool transforms."""

    tools: dict[str, ToolTransformRequest] = Field(default_factory=dict)
    """The multi-tool transform to apply to the tools."""

    def to_transport(self) -> FastMCPTransport:
        """Get the transport for the server."""

        transport: ClientTransport = super().to_transport()  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]

        wrapped_mcp_server = FastMCP.as_proxy(transport)

        [
            wrapped_mcp_server.add_tool_transform(name, transform)
            for name, transform in self.tools.items()
        ]

        return FastMCPTransport(wrapped_mcp_server)


class TransformingStdioMCPServer(WrappedMCPServerMixin, StdioMCPServer):
    """A Stdio server with tool transforms."""


class TransformingRemoteMCPServer(WrappedMCPServerMixin, RemoteMCPServer):
    """A Remote server with tool transforms."""


class TransformingMCPConfig(MCPConfig):
    """A MCP Config with tool transforms."""

    mcpServers: dict[str, TransformingStdioMCPServer | TransformingRemoteMCPServer] = (
        Field(default_factory=dict)
    )
    """The MCP servers."""

    @classmethod
    def _validate_stdio_server(
        cls, server_config: dict[str, Any]
    ) -> TransformingStdioMCPServer:
        """Validate a stdio server configuration."""
        return TransformingStdioMCPServer.model_validate(server_config)

    @classmethod
    def _validate_remote_server(
        cls, server_config: dict[str, Any]
    ) -> TransformingRemoteMCPServer:
        """Validate a remote server configuration."""
        return TransformingRemoteMCPServer.model_validate(server_config)
