import json
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult


@dataclass
class CustomData:
    x: int
    y: int


def custom_serializer(data: Any) -> str:
    if isinstance(data, CustomData):
        return json.dumps({"custom_x": data.x, "custom_y": data.y})
    return str(data)


async def test_tool_custom_serializer():
    """Test that a tool uses its custom serializer."""
    mcp = FastMCP("Test Server")

    @mcp.tool(serializer=custom_serializer)
    def returns_custom_data(x: int, y: int) -> CustomData:
        return CustomData(x=x, y=y)

    tool = await mcp.get_tool("returns_custom_data")
    assert tool.serializer is custom_serializer

    result = await tool.run({"x": 10, "y": 20})
    assert isinstance(result, ToolResult)
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    assert result.content[0].text == '{"custom_x": 10, "custom_y": 20}'


async def test_tool_default_serializer():
    """Test that a tool uses the default serializer when no custom one provided."""
    mcp = FastMCP("Test Server")

    @mcp.tool
    def returns_dict(x: int) -> dict[str, int]:
        return {"val": x}

    tool = await mcp.get_tool("returns_dict")
    assert tool.serializer is None

    result = await tool.run({"x": 10})
    assert isinstance(result, ToolResult)
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    # Default serializer (pydantic_core) just dumps json for dicts
    assert json.loads(result.content[0].text) == {"val": 10}


async def test_tool_serializer_precedence():
    """Test that tool serializer overrides server serializer implies
    LocalProvider keeps tool serializer.

    Note: FastMCP server level serializer injection happens when providers are attached
    or tools added. However, `LocalProvider` handles `tool(..., serializer=...)`
    by storing it on the tool.
    """
    mcp = FastMCP("Test Server", tool_serializer=custom_serializer)

    def serializer1(x):
        return "1"

    @mcp.tool(serializer=serializer1)
    def t1():
        return "data"

    tool = await mcp.get_tool("t1")
    assert tool.serializer is serializer1


async def test_serializer_error_fallback():
    """Test that if serializer fails, we might see a warning or fallback (implementation detail).
    Current implementation of `_serialize_with_fallback` logs warning and uses default.
    """
    mcp = FastMCP("Test Server")

    def failing_serializer(x):
        raise ValueError("Failed to serialize")

    @mcp.tool(serializer=failing_serializer)
    def t2():
        return {"a": 1}

    tool = await mcp.get_tool("t2")

    # It should fall back to default serializer
    result = await tool.run({})
    assert result.content[0].text == '{"a":1}'
