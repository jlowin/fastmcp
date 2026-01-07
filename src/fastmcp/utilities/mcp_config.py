from typing import Any

from fastmcp.client.client import Client
from fastmcp.client.transports import (
    ClientTransport,
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
)
from fastmcp.mcp_config import (
    MCPConfig,
    MCPServerTypes,
)
from fastmcp.server.providers.proxy import FastMCPProxy, ProxyClient
from fastmcp.server.server import FastMCP


def mcp_config_to_servers_and_transports(
    config: MCPConfig,
) -> list[tuple[str, FastMCP[Any], ClientTransport, Client[Any] | None]]:
    """A utility function to convert each entry of an MCP Config into a transport, server, and proxy client.

    Returns:
        A list of tuples containing (name, server, transport, proxy_client).
        The proxy_client is the base client used by proxy servers for making remote calls.
        It may be None for transforming server types that manage their own clients.
    """
    return [
        mcp_server_type_to_servers_and_transports(name, mcp_server)
        for name, mcp_server in config.mcpServers.items()
    ]


def mcp_server_type_to_servers_and_transports(
    name: str,
    mcp_server: MCPServerTypes,
) -> tuple[str, FastMCP[Any], ClientTransport, Client[Any] | None]:
    """A utility function to convert each entry of an MCP Config into a transport, server, and proxy client.

    Returns:
        A tuple of (name, server, transport, proxy_client).
        The proxy_client is the base client used for making remote calls, or None
        for transforming server types that manage their own clients.
    """

    from fastmcp.mcp_config import (
        TransformingRemoteMCPServer,
        TransformingStdioMCPServer,
    )

    server: FastMCP[Any]
    transport: ClientTransport
    proxy_client: Client[Any] | None = None

    client_name = ProxyClient.generate_name(f"MCP_{name}")
    server_name = FastMCPProxy.generate_name(f"MCP_{name}")

    if isinstance(mcp_server, TransformingRemoteMCPServer | TransformingStdioMCPServer):
        server, transport = mcp_server._to_server_and_underlying_transport(
            server_name=server_name, client_name=client_name
        )
        # Transforming servers manage their own clients, so we can't access them here
    else:
        transport = mcp_server.to_transport()
        client: ProxyClient[StreamableHttpTransport | SSETransport | StdioTransport] = (
            ProxyClient(transport=transport, name=client_name)
        )
        proxy_client = client

        server = FastMCP.as_proxy(name=server_name, backend=client)

    return name, server, transport, proxy_client
