"""Core tool transform functionality."""

from dataclasses import dataclass
from typing import Annotated, Any

import pytest
from mcp.types import TextContent
from pydantic import Field

from fastmcp import FastMCP
from fastmcp.client.client import Client
from fastmcp.tools import Tool, forward, forward_raw
from fastmcp.tools.function_tool import FunctionTool
from fastmcp.tools.tool_transform import (
    ArgTransform,
    TransformedTool,
)


def get_property(tool: Tool, name: str) -> dict[str, Any]:
    return tool.parameters["properties"][name]


@pytest.fixture
def add_tool() -> FunctionTool:
    def add(
        old_x: Annotated[int, Field(description="old_x description")], old_y: int = 10
    ) -> int:
        print("running!")
        return old_x + old_y

    return Tool.from_function(add)


def test_tool_from_tool_no_change(add_tool):
    new_tool = Tool.from_tool(add_tool)
    assert isinstance(new_tool, TransformedTool)
    assert new_tool.parameters == add_tool.parameters
    assert new_tool.name == add_tool.name
    assert new_tool.description == add_tool.description


async def test_renamed_arg_description_is_maintained(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_x": ArgTransform(name="new_x")}
    )
    assert (
        new_tool.parameters["properties"]["new_x"]["description"] == "old_x description"
    )


async def test_tool_defaults_are_maintained_on_unmapped_args(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_x": ArgTransform(name="new_x")}
    )
    result = await new_tool.run(arguments={"new_x": 1})
    # The parent tool returns int which gets wrapped as structured output
    assert result.structured_content == {"result": 11}


async def test_tool_defaults_are_maintained_on_mapped_args(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_y": ArgTransform(name="new_y")}
    )
    result = await new_tool.run(arguments={"old_x": 1})
    # The parent tool returns int which gets wrapped as structured output
    assert result.structured_content == {"result": 11}


def test_tool_change_arg_name(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_x": ArgTransform(name="new_x")}
    )

    assert sorted(new_tool.parameters["properties"]) == ["new_x", "old_y"]
    assert get_property(new_tool, "new_x") == get_property(add_tool, "old_x")
    assert get_property(new_tool, "old_y") == get_property(add_tool, "old_y")
    assert new_tool.parameters["required"] == ["new_x"]


def test_tool_change_arg_description(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_x": ArgTransform(description="new description")}
    )
    assert get_property(new_tool, "old_x")["description"] == "new description"


async def test_tool_drop_arg(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_y": ArgTransform(hide=True)}
    )
    assert sorted(new_tool.parameters["properties"]) == ["old_x"]
    result = await new_tool.run(arguments={"old_x": 1})
    assert result.structured_content == {"result": 11}


async def test_dropped_args_error_if_provided(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_y": ArgTransform(hide=True)}
    )
    with pytest.raises(ValueError, match="Unknown argument"):
        await new_tool.run(arguments={"old_x": 1, "old_y": 2})


async def test_hidden_arg_with_constant_default(add_tool):
    new_tool = Tool.from_tool(
        add_tool, transform_args={"old_y": ArgTransform(hide=True)}
    )
    result = await new_tool.run(arguments={"old_x": 1})
    # old_y should use its default value of 10
    assert result.structured_content == {"result": 11}


async def test_hidden_arg_without_default_uses_parent_default(add_tool):
    def func_without_default(x: int, y: int) -> int:
        return x + y

    tool_without_default = Tool.from_function(func_without_default)
    new_tool = Tool.from_tool(
        tool_without_default, transform_args={"y": ArgTransform(hide=True)}
    )
    # y has no default, so it should raise an error
    with pytest.raises(ValueError, match="Missing required argument"):
        await new_tool.run(arguments={"x": 1})


async def test_mixed_hidden_args_with_custom_function(add_tool):
    async def custom_fn(new_x: int, **kwargs) -> str:
        result = await forward(new_x=new_x, **kwargs)
        assert isinstance(result.content[0], TextContent)
        return f"Custom: {result.content[0].text}"

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={
            "old_x": ArgTransform(name="new_x"),
            "old_y": ArgTransform(hide=True),
        },
    )

    result = await new_tool.run(arguments={"new_x": 5})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "Custom: 15"


async def test_hide_required_param_without_default_raises_error():
    def func(x: int, y: int) -> int:
        return x + y

    tool = Tool.from_function(func)

    with pytest.raises(
        ValueError,
        match="Cannot hide required parameter 'y' that has no default value",
    ):
        Tool.from_tool(tool, transform_args={"y": ArgTransform(hide=True)})


async def test_hide_required_param_with_user_default_works():
    def func(x: int, y: int = 20) -> int:
        return x + y

    tool = Tool.from_function(func)
    new_tool = Tool.from_tool(tool, transform_args={"y": ArgTransform(hide=True)})

    result = await new_tool.run(arguments={"x": 5})
    assert result.structured_content == {"result": 25}


async def test_hidden_param_prunes_defs():
    """Test that hidden parameters are pruned from $defs in schema."""

    @dataclass
    class Nested:
        value: int

    def func(x: int, nested: Nested) -> int:
        return x + nested.value

    tool = Tool.from_function(func)
    new_tool = Tool.from_tool(tool, transform_args={"nested": ArgTransform(hide=True)})

    # nested should be hidden, so its $defs should be pruned
    schema = new_tool.parameters
    assert "nested" not in schema["properties"]
    # $defs for Nested should be pruned since nested is hidden
    assert "$defs" not in schema or "Nested" not in schema.get("$defs", {})


async def test_forward_with_argument_mapping(add_tool):
    async def custom_fn(new_x: int, **kwargs) -> str:
        result = await forward(new_x=new_x, **kwargs)
        assert isinstance(result.content[0], TextContent)
        return f"Mapped: {result.content[0].text}"

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={"old_x": ArgTransform(name="new_x")},
    )

    result = await new_tool.run(arguments={"new_x": 3, "old_y": 7})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "Mapped: 10"


async def test_forward_with_incorrect_args_raises_error(add_tool):
    async def custom_fn(new_x: int, **kwargs) -> str:
        # Try to forward with wrong arg name
        result = await forward(old_x=new_x, **kwargs)  # Wrong: should be new_x
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={"old_x": ArgTransform(name="new_x")},
    )

    with pytest.raises(ValueError, match="Unknown argument"):
        await new_tool.run(arguments={"new_x": 3})


async def test_forward_raw_without_argument_mapping(add_tool):
    async def custom_fn(**kwargs) -> str:
        # forward_raw passes through kwargs as-is
        result = await forward_raw(**kwargs)
        assert isinstance(result.content[0], TextContent)
        return f"Raw: {result.content[0].text}"

    new_tool = Tool.from_tool(add_tool, transform_fn=custom_fn)

    result = await new_tool.run(arguments={"old_x": 2, "old_y": 8})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "Raw: 10"


async def test_custom_fn_with_kwargs_and_no_transform_args(add_tool):
    async def custom_fn(**kwargs) -> str:
        result = await forward(**kwargs)
        assert isinstance(result.content[0], TextContent)
        return f"Custom: {result.content[0].text}"

    new_tool = Tool.from_tool(add_tool, transform_fn=custom_fn)

    result = await new_tool.run(arguments={"old_x": 4, "old_y": 6})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "Custom: 10"


async def test_fn_with_kwargs_passes_through_original_args(add_tool):
    async def custom_fn(**kwargs) -> str:
        # Should receive original arg names
        assert "old_x" in kwargs
        assert "old_y" in kwargs
        result = await forward(**kwargs)
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text

    new_tool = Tool.from_tool(add_tool, transform_fn=custom_fn)

    result = await new_tool.run(arguments={"old_x": 1, "old_y": 2})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "3"


async def test_fn_with_kwargs_receives_transformed_arg_names(add_tool):
    async def custom_fn(new_x: int, **kwargs) -> str:
        # Should receive transformed arg name
        assert "new_x" in kwargs or "new_x" == new_x
        result = await forward(new_x=new_x, **kwargs)
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={"old_x": ArgTransform(name="new_x")},
    )

    result = await new_tool.run(arguments={"new_x": 5, "old_y": 3})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "8"


async def test_fn_with_kwargs_handles_partial_explicit_args(add_tool):
    async def custom_fn(new_x: int, **kwargs) -> str:
        result = await forward(new_x=new_x, **kwargs)
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={"old_x": ArgTransform(name="new_x")},
    )

    # Only provide new_x, old_y should use default
    result = await new_tool.run(arguments={"new_x": 7})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "17"  # 7 + 10 (default)


async def test_fn_with_kwargs_mixed_mapped_and_unmapped_args(add_tool):
    async def custom_fn(new_x: int, old_y: int, **kwargs) -> str:
        result = await forward(new_x=new_x, old_y=old_y, **kwargs)
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={"old_x": ArgTransform(name="new_x")},
    )

    result = await new_tool.run(arguments={"new_x": 2, "old_y": 8})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "10"


async def test_fn_with_kwargs_dropped_args_not_in_kwargs(add_tool):
    async def custom_fn(new_x: int, **kwargs) -> str:
        # old_y is dropped, so it shouldn't be in kwargs
        assert "old_y" not in kwargs
        result = await forward(new_x=new_x, **kwargs)
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text

    new_tool = Tool.from_tool(
        add_tool,
        transform_fn=custom_fn,
        transform_args={
            "old_x": ArgTransform(name="new_x"),
            "old_y": ArgTransform(hide=True),
        },
    )

    result = await new_tool.run(arguments={"new_x": 3})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "13"  # 3 + 10 (default for hidden old_y)


async def test_forward_outside_context_raises_error():
    """Test that forward() raises error when called outside transform context."""
    with pytest.raises(RuntimeError, match="forward\(\) can only be called"):
        await forward(x=1)


async def test_forward_raw_outside_context_raises_error():
    """Test that forward_raw() raises error when called outside transform context."""
    with pytest.raises(RuntimeError, match="forward_raw\(\) can only be called"):
        await forward_raw(x=1)


def test_transform_args_with_parent_defaults():
    def parent(x: int, y: int = 10) -> int:
        return x + y

    tool = Tool.from_function(parent)
    new_tool = Tool.from_tool(tool, transform_args={"x": ArgTransform(name="new_x")})

    # new_tool should have old_y with default, and new_x as required
    assert "new_x" in new_tool.parameters["properties"]
    assert "old_y" in new_tool.parameters["properties"]
    assert "new_x" in new_tool.parameters["required"]
    assert "old_y" not in new_tool.parameters["required"]


def test_transform_args_validation_unknown_arg(add_tool):
    with pytest.raises(ValueError, match="Unknown argument"):
        Tool.from_tool(add_tool, transform_args={"unknown": ArgTransform()})


def test_transform_args_creates_duplicate_names(add_tool):
    with pytest.raises(ValueError, match="Duplicate argument name"):
        Tool.from_tool(
            add_tool,
            transform_args={
                "old_x": ArgTransform(name="new_name"),
                "old_y": ArgTransform(name="new_name"),
            },
        )


async def test_function_without_kwargs_missing_params(add_tool):
    def custom_fn(x: int) -> str:
        return f"Result: {x}"

    new_tool = Tool.from_tool(add_tool, transform_fn=custom_fn)

    # custom_fn doesn't have **kwargs, so it can't receive old_y
    # Should raise error when old_y is required but not provided
    with pytest.raises(ValueError, match="Missing required argument"):
        await new_tool.run(arguments={"old_x": 1})


async def test_function_without_kwargs_can_have_extra_params(add_tool):
    def custom_fn(old_x: int, old_y: int, extra: int = 5) -> str:
        return f"Result: {old_x + old_y + extra}"

    new_tool = Tool.from_tool(add_tool, transform_fn=custom_fn)

    result = await new_tool.run(arguments={"old_x": 1, "old_y": 2})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "Result: 8"  # 1 + 2 + 5


async def test_function_with_kwargs_can_add_params(add_tool):
    async def custom_fn(old_x: int, old_y: int, multiplier: int = 2, **kwargs) -> str:
        result = await forward(**kwargs)
        assert isinstance(result.content[0], TextContent)
        base_result = int(result.content[0].text)
        return str(base_result * multiplier)

    new_tool = Tool.from_tool(add_tool, transform_fn=custom_fn)

    result = await new_tool.run(arguments={"old_x": 3, "old_y": 4, "multiplier": 3})
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "21"  # (3 + 4) * 3


class TestProxy:
    @pytest.fixture
    def mcp_server(self) -> FastMCP:
        mcp = FastMCP()

        @mcp.tool
        def add(old_x: int, old_y: int = 10) -> int:
            return old_x + old_y

        return mcp

    @pytest.fixture
    def proxy_server(self, mcp_server: FastMCP) -> FastMCP:
        from fastmcp.client.transports import FastMCPTransport

        proxy = FastMCP.as_proxy(FastMCPTransport(mcp_server))
        return proxy

    async def test_transform_proxy(self, proxy_server: FastMCP):
        # when adding transformed tools to proxy servers. Needs separate investigation.

        add_tool = await proxy_server.get_tool("add")
        assert add_tool is not None
        new_add_tool = Tool.from_tool(
            add_tool,
            name="add_transformed",
            transform_args={"old_x": ArgTransform(name="new_x")},
        )
        proxy_server.add_tool(new_add_tool)

        async with Client(proxy_server) as client:
            # The tool should be registered with its transformed name
            result = await client.call_tool("add_transformed", {"new_x": 1, "old_y": 2})
            assert isinstance(result.content[0], TextContent)
            assert result.content[0].text == "3"
