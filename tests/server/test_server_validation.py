from fastmcp import Client, FastMCP


async def test_server_validation():
    """
    The server should be able to accept an integer as a string
    """
    mcp = FastMCP("Test Server")

    @mcp.tool
    def echo_int(message: int) -> str:
        return f"The number is {message}"

    tools_dict = await mcp._tool_manager.get_tools()
    tools = list(tools_dict.values())
    assert len(tools) == 1

    async with Client(mcp) as client:
        result = await client.call_tool("echo_int", {"message": 20})
        assert result.data == "The number is 20"

        result = await client.call_tool("echo_int", {"message": "20"})
        assert result.data == "The number is 20"
