"""Tests for compatibility tools contrib module."""

import pytest

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.compatibility_tools import (
    add_compatibility_tools,
    get_prompt_tool,
    get_resource_tool,
    list_prompts_tool,
    list_resources_tool,
)


@pytest.fixture
def server_with_resources_and_prompts() -> FastMCP:
    """Create a FastMCP server with sample resources and prompts."""
    mcp = FastMCP("Test Server")

    @mcp.resource("config://settings")
    def get_settings() -> str:
        return "Server configuration data"

    @mcp.resource("data://users")
    def get_users() -> str:
        return "User list data"

    @mcp.prompt()
    def greeting(name: str) -> str:
        """Greet a user by name."""
        return f"Hello, {name}!"

    @mcp.prompt()
    def system_prompt(context: str = "general") -> str:
        """Generate a system prompt."""
        return f"You are a helpful assistant. Context: {context}"

    return mcp


async def test_list_resources_tool_registration(
    server_with_resources_and_prompts: FastMCP,
):
    """Test that list_resources_tool can be added to a server."""
    mcp = server_with_resources_and_prompts
    mcp.add_tool(list_resources_tool)

    tools = await mcp.get_tools()
    assert "list_resources" in tools
    assert tools["list_resources"].name == "list_resources"


async def test_get_resource_tool_registration(
    server_with_resources_and_prompts: FastMCP,
):
    """Test that get_resource_tool can be added to a server."""
    mcp = server_with_resources_and_prompts
    mcp.add_tool(get_resource_tool)

    tools = await mcp.get_tools()
    assert "get_resource" in tools
    assert tools["get_resource"].name == "get_resource"


async def test_list_prompts_tool_registration(
    server_with_resources_and_prompts: FastMCP,
):
    """Test that list_prompts_tool can be added to a server."""
    mcp = server_with_resources_and_prompts
    mcp.add_tool(list_prompts_tool)

    tools = await mcp.get_tools()
    assert "list_prompts" in tools
    assert tools["list_prompts"].name == "list_prompts"


async def test_get_prompt_tool_registration(server_with_resources_and_prompts: FastMCP):
    """Test that get_prompt_tool can be added to a server."""
    mcp = server_with_resources_and_prompts
    mcp.add_tool(get_prompt_tool)

    tools = await mcp.get_tools()
    assert "get_prompt" in tools
    assert tools["get_prompt"].name == "get_prompt"


async def test_add_compatibility_tools(server_with_resources_and_prompts: FastMCP):
    """Test that add_compatibility_tools adds all four tools."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    tools = await mcp.get_tools()
    assert "list_resources" in tools
    assert "get_resource" in tools
    assert "list_prompts" in tools
    assert "get_prompt" in tools


async def test_list_resources_via_client(server_with_resources_and_prompts: FastMCP):
    """Test list_resources tool returns correct data via client."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool("list_resources", {})
        # Check structured content (None because output_schema=None)
        assert result.structured_content is None
        # Check text content
        assert len(result.content) == 1
        content = result.content[0]
        assert hasattr(content, "text")


async def test_get_resource_via_client(server_with_resources_and_prompts: FastMCP):
    """Test get_resource tool returns correct data via client."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool("get_resource", {"uri": "config://settings"})
        # Check that we got content
        assert len(result.content) == 1
        content = result.content[0]
        assert hasattr(content, "text")
        # Verify the data includes expected fields
        import json

        data = json.loads(content.text)  # type: ignore[attr-defined]
        assert data["uri"] == "config://settings"
        assert data["mimeType"] == "text/plain"
        assert "text" in data


async def test_get_resource_nonexistent(server_with_resources_and_prompts: FastMCP):
    """Test get_resource with nonexistent URI raises error."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_resource", {"uri": "nonexistent://resource"}, raise_on_error=False
        )
        # Should return error in is_error
        assert result.is_error is True


async def test_list_prompts_via_client(server_with_resources_and_prompts: FastMCP):
    """Test list_prompts tool returns correct data via client."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool("list_prompts", {})
        assert result.structured_content is None
        assert len(result.content) == 1
        content = result.content[0]
        assert hasattr(content, "text")


async def test_get_prompt_with_args_via_client(
    server_with_resources_and_prompts: FastMCP,
):
    """Test get_prompt tool with arguments via client."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_prompt", {"name": "greeting", "arguments": {"name": "World"}}
        )
        assert len(result.content) == 1
        content = result.content[0]
        assert hasattr(content, "text")
        # Verify the data
        import json

        data = json.loads(content.text)  # type: ignore[attr-defined]
        assert data["name"] == "greeting"
        assert "description" in data
        assert "messages" in data


async def test_get_prompt_without_args_via_client(
    server_with_resources_and_prompts: FastMCP,
):
    """Test get_prompt tool with optional arguments via client."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_prompt",
            {"name": "system_prompt", "arguments": {"context": "testing"}},
        )
        assert len(result.content) == 1
        content = result.content[0]
        assert hasattr(content, "text")
        # Verify the data
        import json

        data = json.loads(content.text)  # type: ignore[attr-defined]
        assert data["name"] == "system_prompt"
        assert "description" in data
        assert "messages" in data


async def test_get_prompt_nonexistent(server_with_resources_and_prompts: FastMCP):
    """Test get_prompt with nonexistent prompt raises error."""
    mcp = server_with_resources_and_prompts
    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_prompt", {"name": "nonexistent"}, raise_on_error=False
        )
        # Should return error in is_error
        assert result.is_error is True


async def test_tools_work_with_mounted_servers():
    """Test that compatibility tools work with mounted servers."""
    # Create a child server with resources
    child = FastMCP("Child Server")

    @child.resource("child://resource")
    def child_resource() -> str:
        return "Child resource data"

    @child.prompt()
    def child_prompt(msg: str) -> str:
        return f"Child prompt: {msg}"

    # Create parent server and mount child
    parent = FastMCP("Parent Server")

    @parent.resource("parent://resource")
    def parent_resource() -> str:
        return "Parent resource data"

    parent.mount(child, "child")
    add_compatibility_tools(parent)

    # Test that tools see both parent and child resources
    async with Client(parent) as client:
        import json

        result = await client.call_tool("list_resources", {})
        resources = json.loads(result.content[0].text)  # type: ignore[attr-defined]
        uris = [r["uri"] for r in resources]
        assert "parent://resource" in uris
        assert "child://resource" in uris

        # Test that tools see both parent and child prompts
        result = await client.call_tool("list_prompts", {})
        # Since output_schema=None, parse the JSON from text content
        import json

        prompts = json.loads(result.content[0].text)  # type: ignore[attr-defined]
        names = [p["name"] for p in prompts]
        # Verify we have both parent and child prompts
        # The child prompt gets a prefix when mounted
        assert len(names) > 0
        assert any("child_prompt" in name for name in names)


async def test_get_resource_basic_functionality():
    """Test get_resource basic functionality."""
    import json

    mcp = FastMCP("Test Server")

    @mcp.resource("test://data")
    def test_data() -> str:
        return "test data content"

    add_compatibility_tools(mcp)

    async with Client(mcp) as client:
        result = await client.call_tool("get_resource", {"uri": "test://data"})
        data = json.loads(result.content[0].text)  # type: ignore[attr-defined]
        assert data["uri"] == "test://data"
        assert "mimeType" in data
        assert "text" in data
