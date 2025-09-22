"""OAuth client example for connecting to FastMCP servers.

This example demonstrates how to connect to an OAuth-protected FastMCP server.

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
            result = await client.call_tool("get_user_profile")
            user_data = result.data
            print(f"AWS Cognito user ID (sub): {user_data.get('user_id', 'N/A')}")
            print(f"Email: {user_data.get('email', 'N/A')}")
            print(f"Email verified: {user_data.get('email_verified', 'N/A')}")
            print(f"Name: {user_data.get('name', 'N/A')}")
            print(f"Cognito groups: {user_data.get('cognito_groups', [])}")

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
