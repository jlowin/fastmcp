"""
Redundant MCP Client - Connects via multiple transports with failover

Demonstrates:
1. In-memory connection (testing)
2. STDIO connection (local server process)
3. HTTP connection (web server)
4. Multi-server configuration
5. Failover between transports
"""

import asyncio
from typing import Any

from fastmcp import Client, FastMCP

# Import the server for in-memory testing
from server import mcp as local_server


class RedundantMCPClient:
    """Client with redundant connection strategies."""

    def __init__(
        self,
        http_url: str | None = None,
        stdio_script: str | None = None,
        in_memory_server: FastMCP | None = None,
    ):
        self.http_url = http_url
        self.stdio_script = stdio_script
        self.in_memory_server = in_memory_server
        self._active_client: Client | None = None
        self._transport_type: str | None = None

    async def connect(self, preferred: str = "memory") -> bool:
        """
        Connect using preferred transport, with fallback.

        Order of preference:
        - "memory": in-memory -> stdio -> http
        - "stdio": stdio -> http -> memory
        - "http": http -> stdio -> memory
        """
        transports = self._get_transport_order(preferred)

        for transport_type, source in transports:
            if source is None:
                continue

            try:
                client = Client(source)
                entered = False
                try:
                    await client.__aenter__()
                    entered = True
                    await client.ping()  # Verify connection
                except Exception as e:
                    if entered:
                        await client.__aexit__(type(e), e, e.__traceback__)
                    raise

                self._active_client = client
                self._transport_type = transport_type
                print(f"Connected via {transport_type}")
                return True
            except Exception as e:
                print(f"Failed to connect via {transport_type}: {e}")
                continue

        print("All connection attempts failed")
        return False

    def _get_transport_order(self, preferred: str) -> list[tuple[str, Any]]:
        """Get transport sources in priority order."""
        all_transports = {
            "memory": ("memory", self.in_memory_server),
            "stdio": ("stdio", self.stdio_script),
            "http": ("http", self.http_url),
        }

        if preferred not in all_transports:
            preferred = "memory"

        # Build ordered list with preferred first
        order = [all_transports[preferred]]
        for key, value in all_transports.items():
            if key != preferred:
                order.append(value)

        return order

    async def disconnect(self):
        """Close the active connection."""
        if self._active_client:
            await self._active_client.__aexit__(None, None, None)
            self._active_client = None
            self._transport_type = None

    async def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        """Call a tool on the connected server."""
        if not self._active_client:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self._active_client.call_tool(name, arguments or {})

    async def list_tools(self) -> list:
        """List available tools."""
        if not self._active_client:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self._active_client.list_tools()

    async def read_resource(self, uri: str) -> Any:
        """Read a resource from the server."""
        if not self._active_client:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self._active_client.read_resource(uri)

    @property
    def transport(self) -> str | None:
        """Current transport type."""
        return self._transport_type

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._active_client is not None


# ============================================================================
# DEMO FUNCTIONS
# ============================================================================


async def demo_in_memory():
    """Demo: In-memory connection (fastest, for testing)."""
    print("\n=== In-Memory Connection Demo ===")

    async with Client(local_server) as client:
        # List tools
        tools = await client.list_tools()
        print(f"Available tools: {[t.name for t in tools]}")

        # Call some tools
        result = await client.call_tool("get_system_info", {})
        print(f"System info: {result.data}")

        result = await client.call_tool("calculate", {"expression": "2 + 2 * 10"})
        print(f"Calculation: {result.data}")

        # Read resources
        status = await client.read_resource("custom://status")
        print(f"Status: {status[0].text}")


async def demo_redundant_client():
    """Demo: Redundant client with failover."""
    print("\n=== Redundant Client Demo ===")

    client = RedundantMCPClient(
        in_memory_server=local_server,
        stdio_script="./server.py",
        http_url="http://localhost:8000/mcp",
    )

    # Connect (will try in-memory first)
    connected = await client.connect(preferred="memory")
    if not connected:
        print("Could not establish any connection")
        return

    print(f"Connected via: {client.transport}")

    # Use the client
    tools = await client.list_tools()
    print(f"Tools available: {len(tools)}")

    result = await client.call_tool("list_directory", {"path": "."})
    print(f"Directory listing: {len(result.data)} entries")

    await client.disconnect()


async def demo_multi_server():
    """Demo: Multi-server configuration."""
    print("\n=== Multi-Server Configuration Demo ===")

    # Configuration for multiple MCP servers
    config = {
        "mcpServers": {
            # Your custom MCP server
            "custom": {
                "command": "python",
                "args": ["./server.py"],
            },
            # Could add more servers here:
            # "weather": {"url": "https://weather-mcp.example.com/mcp"},
            # "database": {"command": "python", "args": ["./db_server.py"]},
        }
    }

    # Note: Multi-server requires actual server processes
    print(f"Config prepared for servers: {list(config['mcpServers'].keys())}")
    print("To use: Client(config) - tools will be prefixed with server names")


async def demo_http_connection():
    """Demo: HTTP connection (requires server running on port 8000)."""
    print("\n=== HTTP Connection Demo ===")
    print("First, start the server in HTTP mode:")
    print("  uv run python server.py --http --port 8000")
    print("")

    try:
        async with Client("http://localhost:8000/mcp") as client:
            await client.ping()
            tools = await client.list_tools()
            print(f"Connected via HTTP! Tools: {[t.name for t in tools]}")
    except Exception as e:
        print(f"HTTP connection failed (expected if server not running): {e}")


async def main():
    """Run all demos."""
    await demo_in_memory()
    await demo_redundant_client()
    await demo_multi_server()
    await demo_http_connection()


if __name__ == "__main__":
    asyncio.run(main())
