"""OAuth client example for connecting to FastMCP servers.

This example demonstrates how to connect to a Keycloak-protected FastMCP server.

To run:
    python client.py
"""

import asyncio

from fastmcp.client import Client

SERVER_URL = "http://localhost:8000/mcp"


async def main():
    try:
        async with Client(SERVER_URL, auth="oauth") as client:
            assert await client.ping()
            print("✅ Successfully authenticated!")

            tools = await client.list_tools()
            print(f"🔧 Available tools ({len(tools)}):")
            for tool in tools:
                print(f"   - {tool.name}: {tool.description}")

            # Test the protected tool
            print("🔒 Calling protected tool: get_access_token_claims")
            result = await client.call_tool("get_access_token_claims")
            user_data = result.data
            print("📄 Available access token claims:")
            print(f"   - sub: {user_data.get('sub', 'N/A')}")
            print(
                f"   - preferred_username: {user_data.get('preferred_username', 'N/A')}"
            )
            print(f"   - email: {user_data.get('email', 'N/A')}")
            print(f"   - realm_access: {user_data.get('realm_access', {})}")

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        raise


if __name__ == "__main__":
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # A dummy IP address to initiate a connection, doesn't need to be reachable.
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        print(f"My Python program is using IP: {ip_address}")
    finally:
        s.close()
    asyncio.run(main())
