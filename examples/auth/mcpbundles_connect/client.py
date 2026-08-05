"""OAuth client example for MCPBundles Connect Auth protected FastMCP servers.

To run:
    python client.py
"""

import asyncio

from fastmcp.client import Client

SERVER_URL = "http://127.0.0.1:8000/mcp"


async def main():
    try:
        async with Client(SERVER_URL, auth="oauth") as client:
            assert await client.ping()
            print("✅ Successfully authenticated with MCPBundles Connect Auth!")

            tools = await client.list_tools()
            print(f"🔧 Available tools ({len(tools)}):")
            for tool in tools:
                print(f"   - {tool.name}: {tool.description}")

            result = await client.call_tool(
                "echo",
                {"message": "Hello from MCPBundles Connect Auth!"},
            )
            print(f"🎯 Echo result: {result}")

            auth_status = await client.call_tool("auth_status", {})
            print(f"👤 Auth status: {auth_status}")

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
