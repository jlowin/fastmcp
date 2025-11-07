"""
Tests to verify all return types work identically with task=True.

These tests ensure that enabling background task support doesn't break
existing functionality - any tool/prompt/resource should work exactly
the same whether task=True or task=False.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel
from typing_extensions import TypedDict

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.utilities.types import Audio, File, Image


class UserData(BaseModel):
    """Example structured output."""

    name: str
    age: int
    active: bool


@pytest.fixture
async def return_type_server():
    """Server with tools that return various types."""
    mcp = FastMCP("return-type-test")

    # String return
    @mcp.tool(task=True)
    async def return_string() -> str:
        return "Hello, World!"

    # Integer return
    @mcp.tool(task=True)
    async def return_int() -> int:
        return 42

    # Float return
    @mcp.tool(task=True)
    async def return_float() -> float:
        return 3.14159

    # Boolean return
    @mcp.tool(task=True)
    async def return_bool() -> bool:
        return True

    # Dict return
    @mcp.tool(task=True)
    async def return_dict() -> dict[str, int]:
        return {"count": 100, "total": 500}

    # List return
    @mcp.tool(task=True)
    async def return_list() -> list[str]:
        return ["apple", "banana", "cherry"]

    # BaseModel return (structured output)
    @mcp.tool(task=True)
    async def return_model() -> UserData:
        return UserData(name="Alice", age=30, active=True)

    # None/null return
    @mcp.tool(task=True)
    async def return_none() -> None:
        return None

    return mcp


async def test_task_string_return(return_type_server):
    """Task mode returns same string as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_string", task=True)
        result = await task
        assert isinstance(result.data, str)
        assert result.data == "Hello, World!"


async def test_task_int_return(return_type_server):
    """Task mode returns same int as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_int", task=True)
        result = await task
        assert isinstance(result.data, int)
        assert result.data == 42


async def test_task_float_return(return_type_server):
    """Task mode returns same float as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_float", task=True)
        result = await task
        assert isinstance(result.data, float)
        assert result.data == 3.14159


async def test_task_bool_return(return_type_server):
    """Task mode returns same bool as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_bool", task=True)
        result = await task
        assert isinstance(result.data, bool)
        assert result.data is True


async def test_task_dict_return(return_type_server):
    """Task mode returns same dict as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_dict", task=True)
        result = await task
        assert isinstance(result.data, dict)
        assert result.data == {"count": 100, "total": 500}


async def test_task_list_return(return_type_server):
    """Task mode returns same list as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_list", task=True)
        result = await task
        assert isinstance(result.data, list)
        assert result.data == ["apple", "banana", "cherry"]


async def test_task_model_return(return_type_server):
    """Task mode returns same BaseModel (as dict) as immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_model", task=True)
        result = await task

        # Client deserializes to dynamic class (type name lost with title pruning)
        assert result.data.__class__.__name__ == "Root"
        assert result.data.name == "Alice"
        assert result.data.age == 30
        assert result.data.active is True


async def test_task_none_return(return_type_server):
    """Task mode handles None return like immediate mode."""
    async with Client(return_type_server) as client:
        task = await client.call_tool("return_none", task=True)
        result = await task
        assert result.data is None


async def test_task_vs_immediate_equivalence(return_type_server):
    """Verify task mode and immediate mode return identical results."""
    async with Client(return_type_server) as client:
        # Test a few types to verify equivalence
        tools_to_test = ["return_string", "return_int", "return_dict"]

        for tool_name in tools_to_test:
            # Call as task
            task = await client.call_tool(tool_name, task=True)
            task_result = await task

            # Call immediately (server should decline background execution when no task meta)
            immediate_result = await client.call_tool(tool_name)

            # Results should be identical
            assert task_result.data == immediate_result.data, (
                f"Mismatch for {tool_name}"
            )


@pytest.fixture
async def prompt_return_server():
    """Server with prompts that return various message structures."""
    mcp = FastMCP("prompt-return-test")

    @mcp.prompt(task=True)
    def single_message_prompt() -> str:
        """Return a single string message."""
        return "Single message content"

    @mcp.prompt(task=True)
    def multi_message_prompt() -> list[str]:
        """Return multiple messages."""
        return [
            "First message",
            "Second message",
            "Third message",
        ]

    return mcp


async def test_prompt_task_single_message(prompt_return_server):
    """Prompt task returns single message correctly."""
    async with Client(prompt_return_server) as client:
        task = await client.get_prompt("single_message_prompt", task=True)
        result = await task

        assert len(result.messages) == 1
        assert result.messages[0].content.text == "Single message content"


async def test_prompt_task_multiple_messages(prompt_return_server):
    """Prompt task returns multiple messages correctly."""
    async with Client(prompt_return_server) as client:
        task = await client.get_prompt("multi_message_prompt", task=True)
        result = await task

        assert len(result.messages) == 3
        assert result.messages[0].content.text == "First message"
        assert result.messages[1].content.text == "Second message"
        assert result.messages[2].content.text == "Third message"


@pytest.fixture
async def resource_return_server():
    """Server with resources that return various content types."""
    mcp = FastMCP("resource-return-test")

    @mcp.resource("text://simple", task=True)
    def simple_text() -> str:
        """Return simple text content."""
        return "Simple text resource"

    @mcp.resource("data://json", task=True)
    def json_data() -> dict[str, Any]:
        """Return JSON-like data."""
        return {"key": "value", "count": 123}

    return mcp


async def test_resource_task_text_content(resource_return_server):
    """Resource task returns text content correctly."""
    async with Client(resource_return_server) as client:
        task = await client.read_resource("text://simple", task=True)
        contents = await task

        assert len(contents) == 1
        assert contents[0].text == "Simple text resource"


async def test_resource_task_json_content(resource_return_server):
    """Resource task returns structured content correctly."""
    async with Client(resource_return_server) as client:
        task = await client.read_resource("data://json", task=True)
        contents = await task

        # Content should be JSON serialized
        assert len(contents) == 1
        import json

        data = json.loads(contents[0].text)
        assert data == {"key": "value", "count": 123}


# ==============================================================================
# Binary & Special Types
# ==============================================================================


@pytest.fixture
async def binary_type_server():
    """Server with tools returning binary and special types."""
    mcp = FastMCP("binary-test")

    @mcp.tool(task=True)
    async def return_bytes() -> bytes:
        return b"Hello bytes!"

    @mcp.tool(task=True)
    async def return_uuid() -> UUID:
        return UUID("12345678-1234-5678-1234-567812345678")

    @mcp.tool(task=True)
    async def return_path() -> Path:
        return Path("/tmp/test.txt")

    @mcp.tool(task=True)
    async def return_datetime() -> datetime:
        return datetime(2025, 11, 5, 12, 30, 45)

    return mcp


async def test_task_bytes_return(binary_type_server):
    """Task mode handles bytes return."""
    async with Client(binary_type_server) as client:
        task = await client.call_tool("return_bytes", task=True)
        result = await task
        assert isinstance(result.data, str)  # bytes serialized to base64 string
        assert "Hello bytes!" in result.data or "SGVsbG8gYnl0ZXMh" in result.data


async def test_task_uuid_return(binary_type_server):
    """Task mode handles UUID return."""
    async with Client(binary_type_server) as client:
        task = await client.call_tool("return_uuid", task=True)
        result = await task
        assert isinstance(result.data, str)
        assert result.data == "12345678-1234-5678-1234-567812345678"


async def test_task_path_return(binary_type_server):
    """Task mode handles Path return."""
    async with Client(binary_type_server) as client:
        task = await client.call_tool("return_path", task=True)
        result = await task
        assert isinstance(result.data, str)
        # Path uses platform-specific separators
        assert "tmp" in result.data and "test.txt" in result.data


async def test_task_datetime_return(binary_type_server):
    """Task mode handles datetime return."""
    async with Client(binary_type_server) as client:
        task = await client.call_tool("return_datetime", task=True)
        result = await task
        assert isinstance(result.data, datetime)
        assert result.data == datetime(2025, 11, 5, 12, 30, 45)


# ==============================================================================
# Collection Varieties
# ==============================================================================


@pytest.fixture
async def collection_server():
    """Server with tools returning various collection types."""
    mcp = FastMCP("collection-test")

    @mcp.tool(task=True)
    async def return_tuple() -> tuple[int, str, bool]:
        return (42, "hello", True)

    @mcp.tool(task=True)
    async def return_set() -> set[int]:
        return {1, 2, 3}

    @mcp.tool(task=True)
    async def return_empty_list() -> list[str]:
        return []

    @mcp.tool(task=True)
    async def return_empty_dict() -> dict[str, Any]:
        return {}

    return mcp


async def test_task_tuple_return(collection_server):
    """Task mode handles tuple return."""
    async with Client(collection_server) as client:
        task = await client.call_tool("return_tuple", task=True)
        result = await task
        assert isinstance(result.data, list)  # Tuples serialize as lists
        assert result.data == [42, "hello", True]


async def test_task_set_return(collection_server):
    """Task mode handles set return."""
    async with Client(collection_server) as client:
        task = await client.call_tool("return_set", task=True)
        result = await task
        assert isinstance(result.data, set)
        assert result.data == {1, 2, 3}


async def test_task_empty_list_return(collection_server):
    """Task mode handles empty list return."""
    async with Client(collection_server) as client:
        task = await client.call_tool("return_empty_list", task=True)
        result = await task
        assert isinstance(result.data, list)
        assert result.data == []


async def test_task_empty_dict_return(collection_server):
    """Task mode handles empty dict return."""
    async with Client(collection_server) as client:
        task = await client.call_tool("return_empty_dict", task=True)
        result = await task
        # Empty structured content becomes None in data
        assert result.data is None
        # But structured content is still {}
        assert result.structured_content == {}


# ==============================================================================
# Media Types (Image, Audio, File)
# ==============================================================================


@pytest.fixture
async def media_server(tmp_path):
    """Server with tools returning media types."""
    mcp = FastMCP("media-test")

    # Create test files
    test_image = tmp_path / "test.png"
    test_image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake png data")

    test_audio = tmp_path / "test.mp3"
    test_audio.write_bytes(b"ID3" + b"fake mp3 data")

    test_file = tmp_path / "test.txt"
    test_file.write_text("test file content")

    @mcp.tool(task=True)
    async def return_image_path() -> Image:
        return Image(path=str(test_image))

    @mcp.tool(task=True)
    async def return_image_data() -> Image:
        return Image(data=test_image.read_bytes(), format="png")

    @mcp.tool(task=True)
    async def return_audio() -> Audio:
        return Audio(path=str(test_audio))

    @mcp.tool(task=True)
    async def return_file() -> File:
        return File(path=str(test_file))

    return mcp


async def test_task_image_path_return(media_server):
    """Task mode handles Image with path."""
    async with Client(media_server) as client:
        task = await client.call_tool("return_image_path", task=True)
        result = await task
        # Image converts to ImageContent
        assert len(result.content) == 1
        assert result.content[0].type == "image"


async def test_task_image_data_return(media_server):
    """Task mode handles Image with data."""
    async with Client(media_server) as client:
        task = await client.call_tool("return_image_data", task=True)
        result = await task
        assert len(result.content) == 1
        assert result.content[0].type == "image"
        assert result.content[0].mimeType == "image/png"


async def test_task_audio_return(media_server):
    """Task mode handles Audio return."""
    async with Client(media_server) as client:
        task = await client.call_tool("return_audio", task=True)
        result = await task
        assert len(result.content) == 1
        # Audio may be returned as text or audio content depending on conversion
        assert result.content[0].type in ["text", "audio"]


async def test_task_file_return(media_server):
    """Task mode handles File return."""
    async with Client(media_server) as client:
        task = await client.call_tool("return_file", task=True)
        result = await task
        assert len(result.content) == 1
        assert result.content[0].type == "resource"


# ==============================================================================
# Structured Types (TypedDict, dataclass, unions)
# ==============================================================================


class PersonTypedDict(TypedDict):
    """Example TypedDict."""

    name: str
    age: int


@dataclass
class PersonDataclass:
    """Example dataclass."""

    name: str
    age: int


@pytest.fixture
async def structured_type_server():
    """Server with tools returning structured types."""
    mcp = FastMCP("structured-test")

    @mcp.tool(task=True)
    async def return_typeddict() -> PersonTypedDict:
        return {"name": "Bob", "age": 25}

    @mcp.tool(task=True)
    async def return_dataclass() -> PersonDataclass:
        return PersonDataclass(name="Charlie", age=35)

    @mcp.tool(task=True)
    async def return_union() -> str | int:
        return "string value"

    @mcp.tool(task=True)
    async def return_union_int() -> str | int:
        return 123

    @mcp.tool(task=True)
    async def return_optional() -> str | None:
        return "has value"

    @mcp.tool(task=True)
    async def return_optional_none() -> str | None:
        return None

    return mcp


async def test_task_typeddict_return(structured_type_server):
    """Task mode handles TypedDict return."""
    async with Client(structured_type_server) as client:
        task = await client.call_tool("return_typeddict", task=True)
        result = await task
        # TypedDict deserializes to dynamic Root class
        assert result.data.name == "Bob"
        assert result.data.age == 25


async def test_task_dataclass_return(structured_type_server):
    """Task mode handles dataclass return."""
    async with Client(structured_type_server) as client:
        task = await client.call_tool("return_dataclass", task=True)
        result = await task
        # Dataclass deserializes to dynamic Root class
        assert result.data.name == "Charlie"
        assert result.data.age == 35


async def test_task_union_str_return(structured_type_server):
    """Task mode handles union type (str branch)."""
    async with Client(structured_type_server) as client:
        task = await client.call_tool("return_union", task=True)
        result = await task
        assert isinstance(result.data, str)
        assert result.data == "string value"


async def test_task_union_int_return(structured_type_server):
    """Task mode handles union type (int branch)."""
    async with Client(structured_type_server) as client:
        task = await client.call_tool("return_union_int", task=True)
        result = await task
        assert isinstance(result.data, int)
        assert result.data == 123


async def test_task_optional_with_value(structured_type_server):
    """Task mode handles Optional[str] with value."""
    async with Client(structured_type_server) as client:
        task = await client.call_tool("return_optional", task=True)
        result = await task
        assert isinstance(result.data, str)
        assert result.data == "has value"


async def test_task_optional_none(structured_type_server):
    """Task mode handles Optional[str] with None."""
    async with Client(structured_type_server) as client:
        task = await client.call_tool("return_optional_none", task=True)
        result = await task
        assert result.data is None


# ==============================================================================
# MCP Content Blocks
# ==============================================================================


@pytest.fixture
async def mcp_content_server(tmp_path):
    """Server with tools returning MCP content blocks."""
    import base64

    from mcp.types import (
        AnyUrl,
        EmbeddedResource,
        ImageContent,
        ResourceLink,
        TextContent,
        TextResourceContents,
    )

    mcp = FastMCP("content-test")

    test_image = tmp_path / "content.png"
    test_image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"content")

    @mcp.tool(task=True)
    async def return_text_content() -> TextContent:
        return TextContent(type="text", text="Direct text content")

    @mcp.tool(task=True)
    async def return_image_content() -> ImageContent:
        return ImageContent(
            type="image",
            data=base64.b64encode(test_image.read_bytes()).decode(),
            mimeType="image/png",
        )

    @mcp.tool(task=True)
    async def return_embedded_resource() -> EmbeddedResource:
        return EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                uri=AnyUrl("test://resource"), text="embedded"
            ),
        )

    @mcp.tool(task=True)
    async def return_resource_link() -> ResourceLink:
        return ResourceLink(
            type="resource_link", uri=AnyUrl("test://linked"), name="Test Resource"
        )

    @mcp.tool(task=True)
    async def return_mixed_content() -> list[TextContent | ImageContent]:
        return [
            TextContent(type="text", text="First block"),
            ImageContent(
                type="image",
                data=base64.b64encode(test_image.read_bytes()).decode(),
                mimeType="image/png",
            ),
            TextContent(type="text", text="Third block"),
        ]

    return mcp


async def test_task_text_content_return(mcp_content_server):
    """Task mode handles TextContent return."""
    async with Client(mcp_content_server) as client:
        task = await client.call_tool("return_text_content", task=True)
        result = await task
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == "Direct text content"


async def test_task_image_content_return(mcp_content_server):
    """Task mode handles ImageContent return."""
    async with Client(mcp_content_server) as client:
        task = await client.call_tool("return_image_content", task=True)
        result = await task
        assert len(result.content) == 1
        assert result.content[0].type == "image"
        assert result.content[0].mimeType == "image/png"


async def test_task_embedded_resource_return(mcp_content_server):
    """Task mode handles EmbeddedResource return."""
    async with Client(mcp_content_server) as client:
        task = await client.call_tool("return_embedded_resource", task=True)
        result = await task
        assert len(result.content) == 1
        assert result.content[0].type == "resource"


async def test_task_resource_link_return(mcp_content_server):
    """Task mode handles ResourceLink return."""
    async with Client(mcp_content_server) as client:
        task = await client.call_tool("return_resource_link", task=True)
        result = await task
        assert len(result.content) == 1
        assert result.content[0].type == "resource_link"
        assert str(result.content[0].uri) == "test://linked"


async def test_task_mixed_content_return(mcp_content_server):
    """Task mode handles mixed content list return."""
    async with Client(mcp_content_server) as client:
        task = await client.call_tool("return_mixed_content", task=True)
        result = await task
        assert len(result.content) == 3
        assert result.content[0].type == "text"
        assert result.content[0].text == "First block"
        assert result.content[1].type == "image"
        assert result.content[2].type == "text"
        assert result.content[2].text == "Third block"
