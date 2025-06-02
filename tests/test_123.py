from fastmcp import Client


async def test_connection():
    client = Client("https://remote.mcpservers.org/fetch/mcp")
    async with client:
        tools = await client.list_tools()
        print(f"Tools: {tools}")
        assert len(tools) > 0
