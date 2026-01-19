"""Tests for tool context injection."""

import base64
import functools
from dataclasses import dataclass

import pytest
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ImageContent,
    TextContent,
)
from pydantic import AnyUrl, BaseModel
from typing_extensions import TypedDict

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import Tool
from fastmcp.utilities.types import Audio, File, Image


def _normalize_anyof_order(schema):
    """Normalize the order of items in anyOf arrays for consistent comparison."""
    if isinstance(schema, dict):
        if "anyOf" in schema:
            schema = schema.copy()
            schema["anyOf"] = sorted(schema["anyOf"], key=str)
        return {k: _normalize_anyof_order(v) for k, v in schema.items()}
    elif isinstance(schema, list):
        return [_normalize_anyof_order(item) for item in schema]
    return schema


class PersonTypedDict(TypedDict):
    name: str
    age: int


class PersonModel(BaseModel):
    name: str
    age: int


@dataclass
class PersonDataclass:
    name: str
    age: int


@pytest.fixture
def tool_server():
    mcp = FastMCP()

    @mcp.tool
    def add(x: int, y: int) -> int:
        return x + y

    @mcp.tool
    def list_tool() -> list[str | int]:
        return ["x", 2]

    @mcp.tool
    def error_tool() -> None:
        raise ValueError("Test error")

    @mcp.tool
    def image_tool(path: str) -> Image:
        return Image(path)

    @mcp.tool
    def audio_tool(path: str) -> Audio:
        return Audio(path)

    @mcp.tool
    def file_tool(path: str) -> File:
        return File(path)

    @mcp.tool
    def mixed_content_tool() -> list[TextContent | ImageContent | EmbeddedResource]:
        return [
            TextContent(type="text", text="Hello"),
            ImageContent(type="image", data="abc", mimeType="application/octet-stream"),
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    blob=base64.b64encode(b"abc").decode(),
                    mimeType="application/octet-stream",
                    uri=AnyUrl("file:///test.bin"),
                ),
            ),
        ]

    @mcp.tool(output_schema=None)
    def mixed_list_fn(image_path: str) -> list:
        return [
            "text message",
            Image(image_path),
            {"key": "value"},
            TextContent(type="text", text="direct content"),
        ]

    @mcp.tool(output_schema=None)
    def mixed_audio_list_fn(audio_path: str) -> list:
        return [
            "text message",
            Audio(audio_path),
            {"key": "value"},
            TextContent(type="text", text="direct content"),
        ]

    @mcp.tool(output_schema=None)
    def mixed_file_list_fn(file_path: str) -> list:
        return [
            "text message",
            File(file_path),
            {"key": "value"},
            TextContent(type="text", text="direct content"),
        ]

    @mcp.tool
    def file_text_tool() -> File:
        return File(data=b"hello world", format="plain")

    return mcp


class TestToolContextInjection:
    """Test context injection in tools."""

    async def test_context_detection(self):
        """Test that context parameters are properly detected and excluded from schema."""
        mcp = FastMCP()

        @mcp.tool
        def tool_with_context(x: int, ctx: Context) -> str:
            return f"Request: {x}"

        tools = await mcp.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "tool_with_context"
        # Context param should not appear in schema
        assert "ctx" not in tools[0].parameters.get("properties", {})

    async def test_context_injection_basic(self):
        """Test that context is properly injected into tool calls."""
        mcp = FastMCP()

        @mcp.tool
        def tool_with_context(x: int, ctx: Context) -> str:
            assert isinstance(ctx, Context)
            return f"Got context with x={x}"

        result = await mcp.call_tool("tool_with_context", {"x": 42})
        assert result.structured_content == {"result": "Got context with x=42"}

    async def test_async_context(self):
        """Test that context works in async functions."""
        mcp = FastMCP()

        @mcp.tool
        async def async_tool(x: int, ctx: Context) -> str:
            assert isinstance(ctx, Context)
            return f"Async with x={x}"

        result = await mcp.call_tool("async_tool", {"x": 42})
        assert result.structured_content == {"result": "Async with x=42"}

    async def test_optional_context(self):
        """Test that context is optional."""
        mcp = FastMCP()

        @mcp.tool
        def no_context(x: int) -> int:
            return x * 2

        result = await mcp.call_tool("no_context", {"x": 21})
        assert result.structured_content == {"result": 42}

    async def test_context_resource_access(self):
        """Test that context can access resources."""
        mcp = FastMCP()

        @mcp.resource("test://data")
        def test_resource() -> str:
            return "resource data"

        @mcp.tool
        async def tool_with_resource(ctx: Context) -> str:
            result = await ctx.read_resource("test://data")
            assert len(result.contents) == 1
            r = result.contents[0]
            return f"Read resource: {r.content} with mime type {r.mime_type}"

        result = await mcp.call_tool("tool_with_resource", {})
        assert result.structured_content == {
            "result": "Read resource: resource data with mime type text/plain"
        }

    async def test_tool_decorator_with_tags(self):
        """Test that the tool decorator properly sets tags."""
        mcp = FastMCP()

        @mcp.tool(tags={"example", "test-tag"})
        def sample_tool(x: int) -> int:
            return x * 2

        tools = await mcp.list_tools()
        assert len(tools) == 1
        assert tools[0].tags == {"example", "test-tag"}

    async def test_callable_object_with_context(self):
        """Test that a callable object can be used as a tool with context."""
        mcp = FastMCP()

        class MyTool:
            async def __call__(self, x: int, ctx: Context) -> int:
                assert isinstance(ctx, Context)
                return x + 1

        mcp.add_tool(Tool.from_function(MyTool(), name="MyTool"))

        result = await mcp.call_tool("MyTool", {"x": 2})
        assert result.structured_content == {"result": 3}

    async def test_decorated_tool_with_functools_wraps(self):
        """Regression test for #2524: @mcp.tool with functools.wraps decorator."""

        def custom_decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        mcp = FastMCP()

        @mcp.tool
        @custom_decorator
        async def decorated_tool(ctx: Context, query: str) -> str:
            assert isinstance(ctx, Context)
            return f"query: {query}"

        tools = await mcp.list_tools()
        tool = next(t for t in tools if t.name == "decorated_tool")
        assert "ctx" not in tool.parameters.get("properties", {})

        result = await mcp.call_tool("decorated_tool", {"query": "test"})
        assert result.structured_content == {"result": "query: test"}
