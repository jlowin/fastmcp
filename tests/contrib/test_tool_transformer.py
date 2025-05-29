from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.types import EmbeddedResource, ImageContent, TextContent

from fastmcp.contrib.tool_transformer.errors import ToolParameterNotFoundError
from fastmcp.contrib.tool_transformer.models import (
    BooleanToolParameter,
    IntToolParameter,
    PostToolCallHookProtocol,
    PreToolCallHookProtocol,
    StringToolParameter,
    ToolParameterTypes,
)
from fastmcp.contrib.tool_transformer.tool_transformer import (
    _apply_hook_parameters,
    _apply_parameter_overrides,
    _create_transformed_function,
    _extract_hook_args,
    transform_tool,
)
from fastmcp.tools import Tool as FastMCPTool


class TestExtractHookArgs:
    async def test_extract_hook_args_no_extra_params(self):
        """Test that when there are no extra parameters, the hook args are empty and the tool args are the original kwargs."""
        extra_parameters = []
        tool_call_kwargs = {"arg1": "val1", "arg2": 123}
        original_kwargs = deepcopy(tool_call_kwargs)

        hook_args, tool_args = _extract_hook_args(extra_parameters, tool_call_kwargs)

        assert hook_args == {}
        assert tool_args == {"arg1": "val1", "arg2": 123}
        assert tool_call_kwargs == original_kwargs, "Input kwargs should not be mutated"

    async def test_extract_hook_args_with_extra_params(self):
        """Test that hook args are properly extracted from the tool args."""

        extra_parameters: list[ToolParameterTypes] = [
            StringToolParameter(name="hook_param_str", description="d", required=True),
            IntToolParameter(name="hook_param_num", description="d", required=False),
        ]
        tool_call_kwargs = {
            "arg1": "val1",
            "hook_param_str": "hook_val_s",
            "hook_param_num": 456,
            "arg2": True,
        }

        hook_args, tool_args = _extract_hook_args(extra_parameters, tool_call_kwargs)

        assert hook_args == {"hook_param_str": "hook_val_s", "hook_param_num": 456}
        assert tool_args == {"arg1": "val1", "arg2": True}

    async def test_extract_hook_args_some_defined_extra_params_not_in_call(self):
        """Test that hook args are properly extracted from the tool args, even if some of the extra parameters are not in the call."""
        extra_parameters: list[ToolParameterTypes] = [
            StringToolParameter(name="hook_param1", description="d1", required=True),
            StringToolParameter(name="hook_param2", description="d2", required=False),
        ]
        tool_call_kwargs = {"arg1": "val1", "hook_param1": "hook_val1"}

        hook_args, tool_args = _extract_hook_args(extra_parameters, tool_call_kwargs)

        assert hook_args == {"hook_param1": "hook_val1"}
        assert tool_args == {"arg1": "val1"}


class TestApplyHookParameters:
    async def test_apply_hook_parameters_no_hooks(self):
        """Test that when there are no hook parameters, the schema is not modified."""
        schema = {"properties": {"a": {"type": "string"}}, "required": ["a"]}
        original_schema = deepcopy(schema)
        hook_parameters = []

        transformed_schema = _apply_hook_parameters(schema, hook_parameters)

        assert transformed_schema == original_schema
        assert schema == original_schema, "Input schema should not be mutated"

    async def test_apply_hook_parameters_add_single_required_hook(self):
        """Test that when there is a single required hook parameter, it is added to the schema."""
        schema = {"properties": {"existing_param": {"type": "integer"}}}

        hook_parameters: list[ToolParameterTypes] = [
            StringToolParameter(name="hp1", description="Hook Param 1", required=True)
        ]

        transformed_schema = _apply_hook_parameters(schema, hook_parameters)

        assert "hp1" in transformed_schema["properties"]
        assert transformed_schema["properties"]["hp1"]["type"] == "string"
        assert transformed_schema["properties"]["hp1"]["description"] == "Hook Param 1"
        assert "hp1" in transformed_schema["required"]
        assert "existing_param" in transformed_schema["properties"]

    async def test_apply_hook_parameters_add_multiple_hooks_optional_and_default(self):
        """Test that when there are multiple hook parameters, they are added to the schema."""
        schema = {"properties": {}}

        hook_parameters: list[ToolParameterTypes] = [
            StringToolParameter(
                name="hp_str",
                description="Hook String",
                required=False,
                default="default_val",
            ),
            IntToolParameter(name="hp_num", description="Hook Number", required=True),
            BooleanToolParameter(
                name="hp_bool", description="Hook Bool", required=False
            ),
        ]

        transformed_schema = _apply_hook_parameters(schema, hook_parameters)

        assert "hp_str" in transformed_schema["properties"]
        assert transformed_schema["properties"]["hp_str"]["default"] == "default_val"
        assert "hp_str" not in transformed_schema.get("required", [])

        assert "hp_num" in transformed_schema["properties"]
        assert "hp_num" in transformed_schema["required"]

        assert "hp_bool" in transformed_schema["properties"]
        assert "default" not in transformed_schema["properties"]["hp_bool"]
        assert "hp_bool" not in transformed_schema.get("required", [])


class TestApplyParameterOverrides:
    async def test_apply_parameter_overrides_no_overrides(self):
        """Test that when there are no parameter overrides, the schema is not modified."""
        schema = {
            "properties": {"param1": {"type": "string", "description": "desc1"}},
            "required": ["param1"],
        }
        original_schema = deepcopy(schema)
        parameter_overrides = []

        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)
        assert transformed_schema == original_schema
        assert schema == original_schema, "Input schema should not be mutated"

    async def test_apply_parameter_overrides_change_description(self):
        """Test that when there is a parameter override, the schema is modified."""
        schema = {"properties": {"p1": {"description": "old_desc", "type": "string"}}}

        parameter_overrides: list[ToolParameterTypes] = [
            StringToolParameter(name="p1", description="new_desc")
        ]

        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)

        assert transformed_schema["properties"]["p1"]["description"] == "new_desc"
        assert transformed_schema["properties"]["p1"]["type"] == "string"

    async def test_apply_parameter_overrides_set_constant(self):
        """Test for `constant` parameter overrides."""
        schema = {"properties": {"p1": {"type": "integer"}}}

        parameter_overrides: list[ToolParameterTypes] = [
            IntToolParameter(name="p1", constant=123)
        ]

        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)
        assert transformed_schema["properties"]["p1"]["const"] == 123

    async def test_apply_parameter_overrides_set_default(self):
        """Test for `default` parameter overrides."""
        schema = {"properties": {"p1": {"type": "string"}}}

        parameter_overrides: list[ToolParameterTypes] = [
            StringToolParameter(name="p1", default="default_val")
        ]

        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)
        assert transformed_schema["properties"]["p1"]["default"] == "default_val"

    async def test_apply_parameter_overrides_required(self):
        """Test for `required` parameter overrides."""
        schema = {"properties": {"p1": {"type": "boolean"}}}  # p1 is optional

        parameter_overrides: list[ToolParameterTypes] = [
            BooleanToolParameter(name="p1", required=True)
        ]
        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)
        assert "p1" in transformed_schema["required"], (
            "Not required parameter should be made required"
        )

        schema = {"properties": {"p1": {"type": "boolean"}}, "required": ["p1"]}

        parameter_overrides: list[ToolParameterTypes] = [
            BooleanToolParameter(name="p1", required=True)
        ]
        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)
        assert "p1" in transformed_schema["required"], (
            "Required parameter should remain required"
        )

        parameter_overrides: list[ToolParameterTypes] = [
            BooleanToolParameter(name="p1", required=False)
        ]
        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)
        assert "p1" in transformed_schema["required"], (
            "You cannot make a required parameter optional"
        )

    async def test_apply_parameter_overrides_non_existent_param_raises_error(self):
        """Test that overriding a non-existent parameter raises an error."""

        schema = {"properties": {"existing": {"type": "string"}}}
        parameter_overrides: list[ToolParameterTypes] = [
            StringToolParameter(name="non_existent_param", description="new")
        ]

        with pytest.raises(ToolParameterNotFoundError) as excinfo:
            _apply_parameter_overrides(schema, parameter_overrides)

        assert "Parameter non_existent_param not found in tool." in str(excinfo.value)

    async def test_apply_parameter_overrides_multiple_overrides(self):
        """Test that multiple parameter overrides are applied correctly."""
        schema = {
            "properties": {
                "p1": {"type": "string", "description": "d1"},
                "p2": {"type": "integer"},
                "p3": {"type": "boolean", "default": False},
            },
            "required": ["p1"],
        }

        parameter_overrides: list[ToolParameterTypes] = [
            StringToolParameter(name="p1", description="new_d1", default="default_p1"),
            IntToolParameter(name="p2", constant=99, required=True),
            BooleanToolParameter(name="p3", required=True),
        ]
        transformed_schema = _apply_parameter_overrides(schema, parameter_overrides)

        assert transformed_schema["properties"]["p1"]["description"] == "new_d1"
        assert transformed_schema["properties"]["p1"]["default"] == "default_p1"
        assert "p1" in transformed_schema["required"]

        assert transformed_schema["properties"]["p2"]["const"] == 99
        assert "p2" in transformed_schema["required"]

        assert "default" in transformed_schema["properties"]["p3"]
        assert "p3" in transformed_schema["required"]


class TestCreateTransformedFunction:
    @pytest.fixture
    def fast_mcp_tool(self) -> FastMCPTool:
        def tool(argument_one: str, argument_two: int):
            return (argument_one, argument_two)

        return FastMCPTool.from_function(tool)

    @pytest.fixture
    def fast_mcp_tool_schema(self) -> dict[str, Any]:
        return {
            "properties": {
                "argument_one": {"type": "string"},
                "argument_two": {"type": "integer"},
            },
            "required": ["argument_one", "argument_two"],
        }

    @pytest.fixture
    def pre_call_hook(self) -> PreToolCallHookProtocol:
        async def pre_call_hook(tool_args: dict[str, Any], hook_args: dict[str, Any]):
            pass

        return pre_call_hook

    @pytest.fixture
    def post_call_hook(self) -> PostToolCallHookProtocol:
        async def post_call_hook(
            response: list[TextContent | ImageContent | EmbeddedResource],
            tool_args: dict[str, Any],
            hook_args: dict[str, Any],
        ):
            pass

        return post_call_hook

    async def test_create_transformed_function_no_hooks(
        self,
        fast_mcp_tool: FastMCPTool,
        fast_mcp_tool_schema: dict[str, Any],
        pre_call_hook: PreToolCallHookProtocol,
        post_call_hook: PostToolCallHookProtocol,
    ):
        """Test that when there are no hooks, the function is created correctly."""

        post_call_hook_mock = AsyncMock(wraps=post_call_hook)
        pre_call_hook_mock = AsyncMock(wraps=pre_call_hook)

        extra_parameters: list[ToolParameterTypes] = [
            StringToolParameter(name="hook_param_str", description="d", required=True),
            IntToolParameter(name="hook_param_num", description="d", required=False),
        ]

        transformed_function = _create_transformed_function(
            fast_mcp_tool.run,
            fast_mcp_tool_schema,
            extra_parameters,
            pre_call_hook_mock,
            post_call_hook_mock,
        )

        result = await transformed_function(
            argument_one="arg1",
            argument_two=123,
            hook_param_str="hook_val_str",
            hook_param_num=456,
        )

        assert isinstance(result, list)
        assert isinstance(result[0], TextContent)
        first_result = result[0]
        assert first_result.text == '[\n  "arg1",\n  123\n]'
        assert first_result.type == "text"

        assert post_call_hook_mock.call_count == 1
        assert pre_call_hook_mock.call_count == 1

        post_call_hook_mock.assert_awaited_once_with(
            result,
            {"argument_one": "arg1", "argument_two": 123},
            {"hook_param_str": "hook_val_str", "hook_param_num": 456},
        )

        pre_call_hook_mock.assert_awaited_once_with(
            {"argument_one": "arg1", "argument_two": 123},
            {"hook_param_str": "hook_val_str", "hook_param_num": 456},
        )


class TestTransformTool:
    @pytest.fixture
    def fast_mcp_tool(self) -> FastMCPTool:
        def tool(argument_one: str, argument_two: int):
            return (argument_one, argument_two)

        return FastMCPTool.from_function(tool)

    @pytest.fixture
    def pre_call_hook(self) -> PreToolCallHookProtocol:
        async def pre_call_hook(tool_args: dict[str, Any], hook_args: dict[str, Any]):
            pass

        return pre_call_hook

    @pytest.fixture
    def post_call_hook(self) -> PostToolCallHookProtocol:
        async def post_call_hook(
            response: list[TextContent | ImageContent | EmbeddedResource],
            tool_args: dict[str, Any],
            hook_args: dict[str, Any],
        ):
            pass

        return post_call_hook

    async def test_transform_tool_no_hooks(self, fast_mcp_tool: FastMCPTool):
        """Test that when there are no hooks, the tool is transformed correctly."""
        transformed_tool = transform_tool(fast_mcp_tool, override=None)
        assert transformed_tool.name == fast_mcp_tool.name
        assert transformed_tool.description == fast_mcp_tool.description
        assert transformed_tool.parameters == fast_mcp_tool.parameters
        assert transformed_tool.annotations == fast_mcp_tool.annotations
        assert transformed_tool.serializer == fast_mcp_tool.serializer

    async def test_transform_tool_parameter_overrides(self, fast_mcp_tool: FastMCPTool):
        """Test that when there are no hooks, the tool is transformed correctly."""

        parameter_overrides: list[ToolParameterTypes] = [
            StringToolParameter(
                name="argument_one", description="new_desc", required=True
            ),
            IntToolParameter(name="argument_two", constant=123, required=False),
        ]

        transformed_tool = transform_tool(
            fast_mcp_tool,
            parameter_overrides=parameter_overrides,
        )
        assert transformed_tool.name == fast_mcp_tool.name
        assert transformed_tool.description == fast_mcp_tool.description
        assert transformed_tool.parameters != fast_mcp_tool.parameters
        assert transformed_tool.annotations == fast_mcp_tool.annotations
        assert transformed_tool.serializer == fast_mcp_tool.serializer

        # you cannot make a required parameter optional, so argument_two stays required
        assert transformed_tool.parameters["required"] == [
            "argument_one",
            "argument_two",
        ]

        properties = transformed_tool.parameters["properties"]

        assert properties["argument_one"]["description"] == "new_desc"
        assert properties["argument_two"]["const"] == 123

    async def test_transform_tool_with_hooks_extra_parameters(
        self,
        fast_mcp_tool: FastMCPTool,
        pre_call_hook: PreToolCallHookProtocol,
        post_call_hook: PostToolCallHookProtocol,
    ):
        """Test that when there are hooks, the tool is transformed correctly."""

        pre_call_hook = AsyncMock(wraps=pre_call_hook)
        post_call_hook = AsyncMock(wraps=post_call_hook)

        hook_parameters: list[ToolParameterTypes] = [
            StringToolParameter(name="hook_param_str", description="d", required=True),
            IntToolParameter(name="hook_param_num", description="d", required=False),
        ]

        transformed_tool = transform_tool(
            fast_mcp_tool,
            hook_parameters=hook_parameters,
            pre_call_hook=pre_call_hook,
            post_call_hook=post_call_hook,
        )
        assert transformed_tool.name == fast_mcp_tool.name
        assert transformed_tool.description == fast_mcp_tool.description
        assert transformed_tool.annotations == fast_mcp_tool.annotations
        assert transformed_tool.serializer == fast_mcp_tool.serializer

        assert transformed_tool.parameters != fast_mcp_tool.parameters

        await transformed_tool.run(
            arguments={
                "argument_one": "arg1",
                "argument_two": 123,
                "hook_param_str": "hook_val_str",
                "hook_param_num": 456,
            }
        )

        assert pre_call_hook.await_count == 1
        assert post_call_hook.await_count == 1

        pre_call_hook.assert_awaited_once_with(
            {"argument_one": "arg1", "argument_two": 123},
            {"hook_param_str": "hook_val_str", "hook_param_num": 456},
        )

    async def test_transform_tool_with_hooks_no_extra_parameters(
        self,
        fast_mcp_tool: FastMCPTool,
        pre_call_hook: PreToolCallHookProtocol,
        post_call_hook: PostToolCallHookProtocol,
    ):
        """Test that when there are hooks, the tool is transformed correctly."""

        pre_call_hook = AsyncMock(wraps=pre_call_hook)
        post_call_hook = AsyncMock(wraps=post_call_hook)

        transformed_tool = transform_tool(
            fast_mcp_tool,
            pre_call_hook=pre_call_hook,
            post_call_hook=post_call_hook,
        )
        assert transformed_tool.name == fast_mcp_tool.name
        assert transformed_tool.description == fast_mcp_tool.description
        assert transformed_tool.parameters == fast_mcp_tool.parameters
        assert transformed_tool.annotations == fast_mcp_tool.annotations
        assert transformed_tool.serializer == fast_mcp_tool.serializer

        await transformed_tool.run(
            arguments={
                "argument_one": "arg1",
                "argument_two": 123,
            }
        )

        assert pre_call_hook.await_count == 1
        assert post_call_hook.await_count == 1

        pre_call_hook.assert_awaited_once_with(
            {"argument_one": "arg1", "argument_two": 123}, {}
        )
