"""Tests for Client(tool_name_prefix=...)."""

import pytest

from fastmcp import Client, FastMCP


@pytest.fixture
def server() -> FastMCP:
    mcp = FastMCP("weather")

    @mcp.tool
    def get_forecast(city: str) -> dict[str, str]:
        return {"city": city, "forecast": "sunny"}

    @mcp.tool
    def get_temperature(city: str) -> int:
        return 72

    return mcp


class TestPrefixedListing:
    async def test_list_tools_applies_prefix(self, server: FastMCP):
        async with Client(server, tool_name_prefix="weather_") as client:
            tools = await client.list_tools()
            assert sorted(t.name for t in tools) == [
                "weather_get_forecast",
                "weather_get_temperature",
            ]

    async def test_prefix_is_literal_no_separator_added(self, server: FastMCP):
        async with Client(server, tool_name_prefix="weather") as client:
            tools = await client.list_tools()
            assert "weatherget_forecast" in {t.name for t in tools}

    async def test_list_tools_mcp_returns_unprefixed_names(self, server: FastMCP):
        async with Client(server, tool_name_prefix="weather_") as client:
            result = await client.list_tools_mcp()
            assert sorted(t.name for t in result.tools) == [
                "get_forecast",
                "get_temperature",
            ]

    async def test_no_prefix_leaves_names_untouched(self, server: FastMCP):
        async with Client(server) as client:
            tools = await client.list_tools()
            assert sorted(t.name for t in tools) == [
                "get_forecast",
                "get_temperature",
            ]


class TestPrefixedCalls:
    async def test_call_tool_accepts_prefixed_name(self, server: FastMCP):
        async with Client(server, tool_name_prefix="weather_") as client:
            result = await client.call_tool("weather_get_forecast", {"city": "Chicago"})
            assert result.data == {"city": "Chicago", "forecast": "sunny"}

    async def test_call_tool_rejects_unprefixed_name(self, server: FastMCP):
        async with Client(server, tool_name_prefix="weather_") as client:
            with pytest.raises(ValueError, match="tool_name_prefix"):
                await client.call_tool("get_forecast", {"city": "Chicago"})

    async def test_call_tool_mcp_uses_unprefixed_names(self, server: FastMCP):
        async with Client(server, tool_name_prefix="weather_") as client:
            result = await client.call_tool_mcp("get_temperature", {"city": "NYC"})
            assert not result.is_error

    async def test_structured_output_parsing_uses_server_name(self, server: FastMCP):
        # Output-schema lookup keys on the server's name; a prefixed call must
        # still deserialize structured content.
        async with Client(server, tool_name_prefix="weather_") as client:
            result = await client.call_tool("weather_get_temperature", {"city": "LA"})
            assert result.data == 72


class TestPrefixConfiguration:
    async def test_new_clone_preserves_prefix(self, server: FastMCP):
        client = Client(server, tool_name_prefix="weather_")
        clone = client.new()
        assert clone.tool_name_prefix == "weather_"
        async with clone:
            tools = await clone.list_tools()
            assert all(t.name.startswith("weather_") for t in tools)
