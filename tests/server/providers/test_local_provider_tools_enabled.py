"""Tests for tool enabled/disabled state."""

import base64
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

from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError
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


class TestToolEnabled:
    async def test_toggle_enabled(self):
        mcp = FastMCP()

        @mcp.tool
        def sample_tool(x: int) -> int:
            return x * 2

        # Tool is enabled by default
        tools = await mcp.list_tools()
        assert any(t.name == "sample_tool" for t in tools)

        # Disable via server
        mcp.disable(names={"sample_tool"}, components={"tool"})

        # Tool should not be in list when disabled
        tools = await mcp.list_tools()
        assert not any(t.name == "sample_tool" for t in tools)

        # Re-enable via server
        mcp.enable(names={"sample_tool"}, components={"tool"})
        tools = await mcp.list_tools()
        assert any(t.name == "sample_tool" for t in tools)

    async def test_tool_disabled_via_server(self):
        mcp = FastMCP()

        @mcp.tool
        def sample_tool(x: int) -> int:
            return x * 2

        mcp.disable(names={"sample_tool"}, components={"tool"})
        tools = await mcp.list_tools()
        assert len(tools) == 0

        with pytest.raises(NotFoundError, match="Unknown tool"):
            await mcp.call_tool("sample_tool", {"x": 5})

    async def test_tool_toggle_enabled(self):
        mcp = FastMCP()

        @mcp.tool
        def sample_tool(x: int) -> int:
            return x * 2

        mcp.disable(names={"sample_tool"}, components={"tool"})
        mcp.enable(names={"sample_tool"}, components={"tool"})
        tools = await mcp.list_tools()
        assert len(tools) == 1

    async def test_tool_toggle_disabled(self):
        mcp = FastMCP()

        @mcp.tool
        def sample_tool(x: int) -> int:
            return x * 2

        mcp.disable(names={"sample_tool"}, components={"tool"})
        tools = await mcp.list_tools()
        assert len(tools) == 0

        with pytest.raises(NotFoundError, match="Unknown tool"):
            await mcp.call_tool("sample_tool", {"x": 5})

    async def test_get_tool_and_disable(self):
        mcp = FastMCP()

        @mcp.tool
        def sample_tool(x: int) -> int:
            return x * 2

        tool = await mcp.get_tool("sample_tool")
        assert tool is not None

        mcp.disable(names={"sample_tool"}, components={"tool"})
        tools = await mcp.list_tools()
        assert len(tools) == 0

        with pytest.raises(NotFoundError, match="Unknown tool"):
            await mcp.call_tool("sample_tool", {"x": 5})

    async def test_cant_call_disabled_tool(self):
        mcp = FastMCP()

        @mcp.tool
        def sample_tool(x: int) -> int:
            return x * 2

        mcp.disable(names={"sample_tool"}, components={"tool"})

        with pytest.raises(NotFoundError, match="Unknown tool"):
            await mcp.call_tool("sample_tool", {"x": 5})
