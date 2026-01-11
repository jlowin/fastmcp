import pytest

from fastmcp import FastMCP
from fastmcp.tools.tool_transform import ToolTransformConfig


async def test_tool_transformation_in_tool_manager():
    """Test that tool transformations are applied in the tool manager."""
    mcp = FastMCP(
        "Test Server",
        tool_transforms={"echo": ToolTransformConfig(name="echo_transformed")},
    )

    @mcp.tool()
    def echo(message: str) -> str:
        """Echo back the message provided."""
        return message

    tools = await mcp.get_tools()
    assert len(tools) == 1
    assert any(t.name == "echo_transformed" for t in tools)
    tool = next(t for t in tools if t.name == "echo_transformed")
    assert tool.name == "echo_transformed"


async def test_transformed_tool_filtering():
    """Test that tool transformations are applied in the tool manager."""
    mcp = FastMCP(
        "Test Server",
        include_tags={"enabled_tools"},
        tool_transforms={
            "echo": ToolTransformConfig(name="echo_transformed", tags={"enabled_tools"})
        },
    )

    @mcp.tool()
    def echo(message: str) -> str:
        """Echo back the message provided."""
        return message

    tools = await mcp.get_tools(run_middleware=True)
    # With transformation applied, the tool now has the enabled_tools tag
    assert len(tools) == 1


async def test_transformed_tool_structured_output_without_annotation():
    """Test that transformed tools generate structured output when original tool has no return annotation.

    Ref: https://github.com/jlowin/fastmcp/issues/1369
    """
    from fastmcp.client import Client

    mcp = FastMCP(
        "Test Server",
        tool_transforms={
            "tool_without_annotation": ToolTransformConfig(name="transformed_tool")
        },
    )

    @mcp.tool()
    def tool_without_annotation(message: str):  # No return annotation
        """A tool without return type annotation."""
        return {"result": "processed", "input": message}

    # Test with client to verify structured output is populated
    async with Client(mcp) as client:
        result = await client.call_tool("transformed_tool", {"message": "test"})

        # Structured output should be populated even without return annotation
        assert result.data is not None
        assert result.data == {"result": "processed", "input": "test"}


# ---------------------------------------------------------------------------
# New API tests (add_tool_transform, tool_transforms property)
# ---------------------------------------------------------------------------


async def test_add_tool_transform():
    """Test that add_tool_transform() works."""
    mcp = FastMCP("Test Server")

    @mcp.tool()
    def my_tool() -> str:
        return "hello"

    # Add transform after tool registration
    mcp.add_tool_transform("my_tool", ToolTransformConfig(name="renamed_tool"))

    tools = await mcp.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "renamed_tool"


async def test_tool_transforms_property():
    """Test that tool_transforms property returns current transforms."""
    mcp = FastMCP("Test Server")

    # Initially empty
    assert mcp.tool_transforms == {}

    # Add transform
    config = ToolTransformConfig(name="renamed")
    mcp.add_tool_transform("my_tool", config)

    # Should reflect the added transform
    assert "my_tool" in mcp.tool_transforms
    assert mcp.tool_transforms["my_tool"].name == "renamed"


async def test_remove_tool_transform():
    """Test that remove_tool_transform() works."""
    mcp = FastMCP("Test Server")

    @mcp.tool()
    def my_tool() -> str:
        return "hello"

    # Add and then remove transform
    mcp.add_tool_transform("my_tool", ToolTransformConfig(name="renamed"))
    mcp.remove_tool_transform("my_tool")

    tools = await mcp.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "my_tool"  # Back to original name


async def test_server_level_transforms_apply_to_mounted_servers():
    """Test that server-level transforms apply to tools from mounted servers."""
    main = FastMCP("Main")
    sub = FastMCP("Sub")

    @sub.tool()
    def sub_tool() -> str:
        return "hello from sub"

    main.mount(sub)

    # Add transform for the mounted tool
    main.add_tool_transform("sub_tool", ToolTransformConfig(name="renamed_sub_tool"))

    tools = await main.get_tools()
    tool_names = [t.name for t in tools]

    assert "renamed_sub_tool" in tool_names
    assert "sub_tool" not in tool_names


async def test_deprecated_add_tool_transformation_warns():
    """Test that add_tool_transformation() emits deprecation warning."""
    mcp = FastMCP("Test Server")

    with pytest.warns(DeprecationWarning, match="add_tool_transformation.*deprecated"):
        mcp.add_tool_transformation("my_tool", ToolTransformConfig(name="renamed"))

    # Should still work
    assert "my_tool" in mcp.tool_transforms


async def test_deprecated_remove_tool_transformation_warns():
    """Test that remove_tool_transformation() emits deprecation warning."""
    mcp = FastMCP("Test Server")
    mcp.add_tool_transform("my_tool", ToolTransformConfig(name="renamed"))

    with pytest.warns(
        DeprecationWarning, match="remove_tool_transformation.*deprecated"
    ):
        mcp.remove_tool_transformation("my_tool")

    # Should still work
    assert "my_tool" not in mcp.tool_transforms


async def test_deprecated_tool_transformations_kwarg_warns():
    """Test that tool_transformations kwarg emits deprecation warning."""
    with pytest.warns(DeprecationWarning, match="tool_transformations.*deprecated"):
        mcp = FastMCP(
            "Test Server",
            tool_transformations={"my_tool": ToolTransformConfig(name="renamed")},
        )

    # Should still work
    assert "my_tool" in mcp.tool_transforms
