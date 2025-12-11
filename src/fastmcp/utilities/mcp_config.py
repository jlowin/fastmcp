import asyncio
from typing import Any

from exceptiongroup import ExceptionGroup

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
from fastmcp.server.proxy import FastMCPProxy, ProxyClient
from fastmcp.server.server import FastMCP


def mcp_config_to_servers_and_transports(
    config: MCPConfig,
) -> list[tuple[str, FastMCP[Any], ClientTransport]]:
    """A utility function to convert each entry of an MCP Config into a transport and server."""
    return [
        mcp_server_type_to_servers_and_transports(name, mcp_server)
        for name, mcp_server in config.mcpServers.items()
    ]


async def warm_up_mcp_config_transports(
    transports: list[ClientTransport],
    server_names: list[str] | None = None,
    show_startup_logs: bool = True,
) -> None:
    """Pre-connect all transports concurrently.

    Connects all stdio transports in parallel for faster initialization. When enabled,
    captures and displays each server's startup logs sequentially for readability.

    Args:
        transports: List of ClientTransport objects to warm up
        server_names: Optional list of server names for log formatting
        show_startup_logs: If True, displays buffered startup logs sequentially
    """
    import tempfile
    from pathlib import Path

    from fastmcp.client.transports import StdioTransport

    if not transports:
        return

    server_names = server_names or [f"server_{i}" for i in range(len(transports))]

    async def connect_with_log_capture(
        transport: ClientTransport, name: str, index: int
    ) -> tuple[int, str, Exception | None]:
        """Connect a transport and capture its startup logs."""
        if not isinstance(transport, StdioTransport):
            return (index, "", None)

        original_log_file = transport.log_file
        temp_log_path = None

        try:
            if show_startup_logs:
                with tempfile.NamedTemporaryFile(
                    mode="w", delete=False, suffix=f"_{name}.log"
                ) as f:
                    temp_log_path = Path(f.name)
                transport.log_file = temp_log_path

            await transport.connect()

            logs = ""
            if temp_log_path and temp_log_path.exists():
                logs = temp_log_path.read_text()
                temp_log_path.unlink()
            return (index, logs, None)

        except Exception as e:
            logs = ""
            if temp_log_path and temp_log_path.exists():
                try:
                    logs = temp_log_path.read_text()
                    temp_log_path.unlink()
                except Exception:
                    pass
            return (index, logs, e)

        finally:
            transport.log_file = original_log_file

    # Connect all transports concurrently
    tasks = [
        asyncio.create_task(connect_with_log_capture(t, name, i))
        for i, (t, name) in enumerate(zip(transports, server_names, strict=False))
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    # Display logs sequentially
    if show_startup_logs:
        _display_startup_logs(results, server_names)

    # Raise if any failed
    errors = [error for _, _, error in results if error is not None]
    if errors:
        raise ExceptionGroup("Failed to start MCP servers", errors)


def _display_startup_logs(
    results: list[tuple[int, str, Exception | None]], server_names: list[str]
) -> None:
    """Display captured startup logs in a readable format."""
    import sys

    for index, logs, error in sorted(results, key=lambda x: x[0]):
        name = server_names[index]

        if logs or error:
            print(
                f"\n{'=' * 60}\n[{name}] Startup\n{'=' * 60}",
                file=sys.stderr,
                flush=True,
            )

            if logs:
                print(logs, file=sys.stderr, end="", flush=True)

            status = "❌ ERROR: " + str(error) if error else "✓ Connected successfully"
            print(f"\n{status}", file=sys.stderr, flush=True)

    # Summary
    total = len(results)
    failed = sum(1 for _, _, error in results if error)
    succeeded = total - failed

    print(
        f"\n{'=' * 60}\nStartup Summary: {succeeded}/{total} servers connected",
        file=sys.stderr,
        flush=True,
    )
    if failed > 0:
        print(f"⚠️  {failed} server(s) failed to start", file=sys.stderr, flush=True)
    print(f"{'=' * 60}\n", file=sys.stderr, flush=True)


def mcp_server_type_to_servers_and_transports(
    name: str,
    mcp_server: MCPServerTypes,
) -> tuple[str, FastMCP[Any], ClientTransport]:
    """A utility function to convert each entry of an MCP Config into a transport and server."""
    from fastmcp.mcp_config import (
        TransformingRemoteMCPServer,
        TransformingStdioMCPServer,
    )

    client_name = ProxyClient.generate_name(f"MCP_{name}")
    server_name = FastMCPProxy.generate_name(f"MCP_{name}")

    if isinstance(mcp_server, TransformingRemoteMCPServer | TransformingStdioMCPServer):
        server, transport = mcp_server._to_server_and_underlying_transport(
            server_name=server_name, client_name=client_name
        )
    else:
        transport = mcp_server.to_transport()
        client: ProxyClient[StreamableHttpTransport | SSETransport | StdioTransport] = (
            ProxyClient(transport=transport, name=client_name)
        )
        server = FastMCP.as_proxy(name=server_name, backend=client)

    return name, server, transport
