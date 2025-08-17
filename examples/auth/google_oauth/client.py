"""OAuth client example for connecting to FastMCP servers.

This example demonstrates how to connect to an OAuth-protected FastMCP server.

To run:
    python client.py
"""

import asyncio

from fastmcp.client import Client

SERVER_URL = "http://127.0.0.1:8000/mcp"


async def main():
    async with Client(SERVER_URL, auth="oauth") as client:
        assert await client.ping()
        print("✅ Successfully authenticated!")

        tools = await client.list_tools()
        print(f"🔧 Available tools ({len(tools)}):")
        for tool in tools:
            print(f"   - {tool.name}: {tool.description}")


if __name__ == "__main__":
    asyncio.run(main())
