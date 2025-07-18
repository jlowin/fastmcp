from typing import Annotated

import pytest
from mcp import McpError
from pydantic import Field

import json
import sqlite3
import tempfile
import time
import urllib.request
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from fastmcp import Client, FastMCP
from fastmcp.exceptions import NotFoundError
from fastmcp.prompts.prompt import FunctionPrompt, Prompt
from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.server.server import (
    OAuth2Storage, 
    _sanitize_metadata_response, 
    _sanitize_oauth_metadata,
    add_resource_prefix,
    has_resource_prefix,
    remove_resource_prefix,
)
from fastmcp.tools import FunctionTool
from fastmcp.tools.tool import Tool


class TestCreateServer:
    async def test_create_server(self):
        mcp = FastMCP(instructions="Server instructions")
        assert mcp.name == "FastMCP"
        assert mcp.instructions == "Server instructions"

    async def test_non_ascii_description(self):
        """Test that FastMCP handles non-ASCII characters in descriptions correctly"""
        mcp = FastMCP()

        @mcp.tool(
            description=(
                "🌟 This tool uses emojis and UTF-8 characters: á é í ó ú ñ 漢字 🎉"
            )
        )
        def hello_world(name: str = "世界") -> str:
            return f"¡Hola, {name}! 👋"

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 1
            tool = tools[0]
            assert tool.description is not None
            assert "🌟" in tool.description
            assert "漢字" in tool.description
            assert "🎉" in tool.description

            result = await client.call_tool("hello_world", {})
            assert result.data == "¡Hola, 世界! 👋"


class TestTools:
    async def test_mcp_tool_name(self):
        """Test MCPTool name for add_tool (key != tool.name)."""

        mcp = FastMCP()

        @mcp.tool
        def fn(x: int) -> int:
            return x + 1

        mcp_tools = await mcp._mcp_list_tools()
        assert len(mcp_tools) == 1
        assert mcp_tools[0].name == "fn"

    async def test_mcp_tool_custom_name(self):
        """Test MCPTool name for add_tool (key != tool.name)."""

        mcp = FastMCP()

        @mcp.tool(name="custom_name")
        def fn(x: int) -> int:
            return x + 1

        mcp_tools = await mcp._mcp_list_tools()
        assert len(mcp_tools) == 1
        assert mcp_tools[0].name == "custom_name"

    async def test_remove_tool_successfully(self):
        """Test that FastMCP.remove_tool removes the tool from the registry."""

        mcp = FastMCP()

        @mcp.tool(name="adder")
        def add(a: int, b: int) -> int:
            return a + b

        mcp_tools = await mcp.get_tools()
        assert "adder" in mcp_tools

        mcp.remove_tool("adder")
        mcp_tools = await mcp.get_tools()
        assert "adder" not in mcp_tools

        with pytest.raises(NotFoundError, match="Unknown tool: adder"):
            await mcp._mcp_call_tool("adder", {"a": 1, "b": 2})

    async def test_add_tool_at_init(self):
        def f(x: int) -> int:
            return x + 1

        def g(x: int) -> int:
            """add two to a number"""
            return x + 2

        g_tool = FunctionTool.from_function(g, name="g-tool")

        mcp = FastMCP(tools=[f, g_tool])

        tools = await mcp.get_tools()
        assert len(tools) == 2
        assert tools["f"].name == "f"
        assert tools["g-tool"].name == "g-tool"
        assert tools["g-tool"].description == "add two to a number"


class TestToolDecorator:
    async def test_no_tools_before_decorator(self):
        mcp = FastMCP()

        with pytest.raises(NotFoundError, match="Unknown tool: add"):
            await mcp._mcp_call_tool("add", {"x": 1, "y": 2})

    async def test_tool_decorator(self):
        mcp = FastMCP()

        @mcp.tool
        def add(x: int, y: int) -> int:
            return x + y

        async with Client(mcp) as client:
            result = await client.call_tool("add", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_without_parentheses(self):
        """Test that @tool decorator works without parentheses."""
        mcp = FastMCP()

        # Test the @tool syntax without parentheses
        @mcp.tool
        def add(x: int, y: int) -> int:
            return x + y

        # Verify the tool was registered correctly
        tools = await mcp.get_tools()
        assert "add" in tools

        # Verify it can be called
        async with Client(mcp) as client:
            result = await client.call_tool("add", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_with_name(self):
        mcp = FastMCP()

        @mcp.tool(name="custom-add")
        def add(x: int, y: int) -> int:
            return x + y

        async with Client(mcp) as client:
            result = await client.call_tool("custom-add", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_with_description(self):
        mcp = FastMCP()

        @mcp.tool(description="Add two numbers")
        def add(x: int, y: int) -> int:
            return x + y

        tools = await mcp._mcp_list_tools()
        assert len(tools) == 1
        tool = tools[0]
        assert tool.description == "Add two numbers"

    async def test_tool_decorator_instance_method(self):
        mcp = FastMCP()

        class MyClass:
            def __init__(self, x: int):
                self.x = x

            def add(self, y: int) -> int:
                return self.x + y

        obj = MyClass(10)
        mcp.add_tool(Tool.from_function(obj.add))
        async with Client(mcp) as client:
            result = await client.call_tool("add", {"y": 2})
            assert result.data == 12

    async def test_tool_decorator_classmethod(self):
        mcp = FastMCP()

        class MyClass:
            x: int = 10

            @classmethod
            def add(cls, y: int) -> int:
                return cls.x + y

        mcp.add_tool(Tool.from_function(MyClass.add))
        async with Client(mcp) as client:
            result = await client.call_tool("add", {"y": 2})
            assert result.data == 12

    async def test_tool_decorator_staticmethod(self):
        mcp = FastMCP()

        class MyClass:
            @mcp.tool
            @staticmethod
            def add(x: int, y: int) -> int:
                return x + y

        async with Client(mcp) as client:
            result = await client.call_tool("add", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_async_function(self):
        mcp = FastMCP()

        @mcp.tool
        async def add(x: int, y: int) -> int:
            return x + y

        async with Client(mcp) as client:
            result = await client.call_tool("add", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_classmethod_error(self):
        mcp = FastMCP()

        with pytest.raises(ValueError, match="To decorate a classmethod"):

            class MyClass:
                @mcp.tool
                @classmethod
                def add(cls, y: int) -> None:
                    pass

    async def test_tool_decorator_classmethod_async_function(self):
        mcp = FastMCP()

        class MyClass:
            x = 10

            @classmethod
            async def add(cls, y: int) -> int:
                return cls.x + y

        mcp.add_tool(Tool.from_function(MyClass.add))
        async with Client(mcp) as client:
            result = await client.call_tool("add", {"y": 2})
            assert result.data == 12

    async def test_tool_decorator_staticmethod_async_function(self):
        mcp = FastMCP()

        class MyClass:
            @staticmethod
            async def add(x: int, y: int) -> int:
                return x + y

        mcp.add_tool(Tool.from_function(MyClass.add))
        async with Client(mcp) as client:
            result = await client.call_tool("add", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_staticmethod_order(self):
        """Test that the recommended decorator order works for static methods"""
        mcp = FastMCP()

        class MyClass:
            @mcp.tool
            @staticmethod
            def add_v1(x: int, y: int) -> int:
                return x + y

        # Test that the recommended order works
        async with Client(mcp) as client:
            result = await client.call_tool("add_v1", {"x": 1, "y": 2})
            assert result.data == 3

    async def test_tool_decorator_with_tags(self):
        """Test that the tool decorator properly sets tags."""
        mcp = FastMCP()

        @mcp.tool(tags={"example", "test-tag"})
        def sample_tool(x: int) -> int:
            return x * 2

        # Verify the tags were set correctly
        tools = await mcp._tool_manager.list_tools()
        assert len(tools) == 1
        assert tools[0].tags == {"example", "test-tag"}

    async def test_add_tool_with_custom_name(self):
        """Test adding a tool with a custom name using server.add_tool()."""
        mcp = FastMCP()

        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        mcp.add_tool(Tool.from_function(multiply, name="custom_multiply"))

        # Check that the tool is registered with the custom name
        tools = await mcp.get_tools()
        assert "custom_multiply" in tools

        # Call the tool by its custom name
        async with Client(mcp) as client:
            result = await client.call_tool("custom_multiply", {"a": 5, "b": 3})
            assert result.data == 15

        # Original name should not be registered
        assert "multiply" not in tools

    async def test_tool_with_annotated_arguments(self):
        """Test that tools with annotated arguments work correctly."""
        mcp = FastMCP()

        @mcp.tool
        def add(
            x: Annotated[int, Field(description="x is an int")],
            y: Annotated[str, Field(description="y is not an int")],
        ) -> None:
            pass

        tool = (await mcp.get_tools())["add"]
        assert tool.parameters["properties"]["x"]["description"] == "x is an int"
        assert tool.parameters["properties"]["y"]["description"] == "y is not an int"

    async def test_tool_with_field_defaults(self):
        """Test that tools with annotated arguments work correctly."""
        mcp = FastMCP()

        @mcp.tool
        def add(
            x: int = Field(description="x is an int"),
            y: str = Field(description="y is not an int"),
        ) -> None:
            pass

        tool = (await mcp.get_tools())["add"]
        assert tool.parameters["properties"]["x"]["description"] == "x is an int"
        assert tool.parameters["properties"]["y"]["description"] == "y is not an int"

    async def test_tool_direct_function_call(self):
        """Test that tools can be registered via direct function call."""
        mcp = FastMCP()

        def standalone_function(x: int, y: int) -> int:
            """A standalone function to be registered."""
            return x + y

        # Register it directly using the new syntax
        result_fn = mcp.tool(standalone_function, name="direct_call_tool")

        # The function should be returned unchanged
        assert isinstance(result_fn, FunctionTool)

        # Verify the tool was registered correctly
        tools = await mcp.get_tools()
        assert tools["direct_call_tool"] is result_fn

        # Verify it can be called
        async with Client(mcp) as client:
            result = await client.call_tool("direct_call_tool", {"x": 5, "y": 3})
            assert result.data == 8

    async def test_tool_decorator_with_string_name(self):
        """Test that @tool("custom_name") syntax works correctly."""
        mcp = FastMCP()

        @mcp.tool("string_named_tool")
        def my_function(x: int) -> str:
            """A function with a string name."""
            return f"Result: {x}"

        # Verify the tool was registered with the custom name
        tools = await mcp.get_tools()
        assert "string_named_tool" in tools
        assert "my_function" not in tools  # Original name should not be registered

        # Verify it can be called
        async with Client(mcp) as client:
            result = await client.call_tool("string_named_tool", {"x": 42})
            assert result.data == "Result: 42"

    async def test_tool_decorator_conflicting_names_error(self):
        """Test that providing both positional and keyword name raises an error."""
        mcp = FastMCP()

        with pytest.raises(
            TypeError,
            match="Cannot specify both a name as first argument and as keyword argument",
        ):

            @mcp.tool("positional_name", name="keyword_name")
            def my_function(x: int) -> str:
                return f"Result: {x}"

    async def test_tool_decorator_with_output_schema(self):
        mcp = FastMCP()

        with pytest.raises(
            ValueError, match='Output schemas must have "type" set to "object"'
        ):

            @mcp.tool(output_schema={"type": "integer"})
            def my_function(x: int) -> str:
                return f"Result: {x}"


class TestResourceDecorator:
    async def test_no_resources_before_decorator(self):
        mcp = FastMCP()

        with pytest.raises(McpError, match="Unknown resource"):
            async with Client(mcp) as client:
                await client.read_resource("resource://data")

    async def test_resource_decorator(self):
        mcp = FastMCP()

        @mcp.resource("resource://data")
        def get_data() -> str:
            return "Hello, world!"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "Hello, world!"  # type: ignore[attr-defined]

    async def test_resource_decorator_incorrect_usage(self):
        mcp = FastMCP()

        with pytest.raises(
            TypeError, match="The @resource decorator was used incorrectly"
        ):

            @mcp.resource  # Missing parentheses #type: ignore
            def get_data() -> str:
                return "Hello, world!"

    async def test_resource_decorator_with_name(self):
        mcp = FastMCP()

        @mcp.resource("resource://data", name="custom-data")
        def get_data() -> str:
            return "Hello, world!"

        resources_dict = await mcp.get_resources()
        resources = list(resources_dict.values())
        assert len(resources) == 1
        assert resources[0].name == "custom-data"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "Hello, world!"  # type: ignore[attr-defined]

    async def test_resource_decorator_with_description(self):
        mcp = FastMCP()

        @mcp.resource("resource://data", description="Data resource")
        def get_data() -> str:
            return "Hello, world!"

        resources_dict = await mcp.get_resources()
        resources = list(resources_dict.values())
        assert len(resources) == 1
        assert resources[0].description == "Data resource"

    async def test_resource_decorator_with_tags(self):
        """Test that the resource decorator properly sets tags."""
        mcp = FastMCP()

        @mcp.resource("resource://data", tags={"example", "test-tag"})
        def get_data() -> str:
            return "Hello, world!"

        resources_dict = await mcp.get_resources()
        resources = list(resources_dict.values())
        assert len(resources) == 1
        assert resources[0].tags == {"example", "test-tag"}

    async def test_resource_decorator_instance_method(self):
        mcp = FastMCP()

        class MyClass:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def get_data(self) -> str:
                return f"{self.prefix} Hello, world!"

        obj = MyClass("My prefix:")

        mcp.add_resource(
            Resource.from_function(
                obj.get_data, uri="resource://data", name="instance-resource"
            )
        )

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "My prefix: Hello, world!"  # type: ignore[attr-defined]

    async def test_resource_decorator_classmethod(self):
        mcp = FastMCP()

        class MyClass:
            prefix = "Class prefix:"

            @classmethod
            def get_data(cls) -> str:
                return f"{cls.prefix} Hello, world!"

        mcp.add_resource(
            Resource.from_function(
                MyClass.get_data, uri="resource://data", name="class-resource"
            )
        )

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "Class prefix: Hello, world!"  # type: ignore[attr-defined]

    async def test_resource_decorator_classmethod_error(self):
        mcp = FastMCP()

        with pytest.raises(ValueError, match="To decorate a classmethod"):

            class MyClass:
                @mcp.resource("resource://data")
                @classmethod
                def get_data(cls) -> None:
                    pass

    async def test_resource_decorator_staticmethod(self):
        mcp = FastMCP()

        class MyClass:
            @mcp.resource("resource://data")
            @staticmethod
            def get_data() -> str:
                return "Static Hello, world!"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "Static Hello, world!"  # type: ignore[attr-defined]

    async def test_resource_decorator_async_function(self):
        mcp = FastMCP()

        @mcp.resource("resource://data")
        async def get_data() -> str:
            return "Async Hello, world!"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "Async Hello, world!"  # type: ignore[attr-defined]

    async def test_resource_decorator_staticmethod_order(self):
        """Test that both decorator orders work for static methods"""
        mcp = FastMCP()

        class MyClass:
            @mcp.resource("resource://data")  # type: ignore[misc]  # Type checker warns but runtime works
            @staticmethod
            def get_data() -> str:
                return "Static Hello, world!"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://data")
            assert result[0].text == "Static Hello, world!"  # type: ignore[attr-defined]


class TestTemplateDecorator:
    async def test_template_decorator(self):
        mcp = FastMCP()

        @mcp.resource("resource://{name}/data")
        def get_data(name: str) -> str:
            return f"Data for {name}"

        templates_dict = await mcp.get_resource_templates()
        templates = list(templates_dict.values())
        assert len(templates) == 1
        assert templates[0].name == "get_data"
        assert templates[0].uri_template == "resource://{name}/data"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://test/data")
            assert result[0].text == "Data for test"  # type: ignore[attr-defined]

    async def test_template_decorator_incorrect_usage(self):
        mcp = FastMCP()

        with pytest.raises(
            TypeError, match="The @resource decorator was used incorrectly"
        ):

            @mcp.resource  # Missing parentheses #type: ignore
            def get_data(name: str) -> str:
                return f"Data for {name}"

    async def test_template_decorator_with_name(self):
        mcp = FastMCP()

        @mcp.resource("resource://{name}/data", name="custom-template")
        def get_data(name: str) -> str:
            return f"Data for {name}"

        templates_dict = await mcp.get_resource_templates()
        templates = list(templates_dict.values())
        assert len(templates) == 1
        assert templates[0].name == "custom-template"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://test/data")
        assert result[0].text == "Data for test"  # type: ignore[attr-defined]

    async def test_template_decorator_with_description(self):
        mcp = FastMCP()

        @mcp.resource("resource://{name}/data", description="Template description")
        def get_data(name: str) -> str:
            return f"Data for {name}"

        templates_dict = await mcp.get_resource_templates()
        templates = list(templates_dict.values())
        assert len(templates) == 1
        assert templates[0].description == "Template description"

    async def test_template_decorator_instance_method(self):
        mcp = FastMCP()

        class MyClass:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def get_data(self, name: str) -> str:
                return f"{self.prefix} Data for {name}"

        obj = MyClass("My prefix:")
        template = ResourceTemplate.from_function(
            obj.get_data,
            uri_template="resource://{name}/data",
            name="instance-template",
        )
        mcp.add_template(template)

        async with Client(mcp) as client:
            result = await client.read_resource("resource://test/data")
            assert result[0].text == "My prefix: Data for test"  # type: ignore[attr-defined]

    async def test_template_decorator_classmethod(self):
        mcp = FastMCP()

        class MyClass:
            prefix = "Class prefix:"

            @classmethod
            def get_data(cls, name: str) -> str:
                return f"{cls.prefix} Data for {name}"

        template = ResourceTemplate.from_function(
            MyClass.get_data,
            uri_template="resource://{name}/data",
            name="class-template",
        )
        mcp.add_template(template)

        async with Client(mcp) as client:
            result = await client.read_resource("resource://test/data")
            assert result[0].text == "Class prefix: Data for test"  # type: ignore[attr-defined]

    async def test_template_decorator_staticmethod(self):
        mcp = FastMCP()

        class MyClass:
            @mcp.resource("resource://{name}/data")
            @staticmethod
            def get_data(name: str) -> str:
                return f"Static Data for {name}"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://test/data")
            assert result[0].text == "Static Data for test"  # type: ignore[attr-defined]

    async def test_template_decorator_async_function(self):
        mcp = FastMCP()

        @mcp.resource("resource://{name}/data")
        async def get_data(name: str) -> str:
            return f"Async Data for {name}"

        async with Client(mcp) as client:
            result = await client.read_resource("resource://test/data")
            assert result[0].text == "Async Data for test"  # type: ignore[attr-defined]

    async def test_template_decorator_with_tags(self):
        """Test that the template decorator properly sets tags."""
        mcp = FastMCP()

        @mcp.resource("resource://{param}", tags={"template", "test-tag"})
        def template_resource(param: str) -> str:
            return f"Template resource: {param}"

        templates_dict = await mcp.get_resource_templates()
        template = templates_dict["resource://{param}"]
        assert template.tags == {"template", "test-tag"}

    async def test_template_decorator_wildcard_param(self):
        mcp = FastMCP()

        @mcp.resource("resource://{param*}")
        def template_resource(param: str) -> str:
            return f"Template resource: {param}"

        templates_dict = await mcp.get_resource_templates()
        template = templates_dict["resource://{param*}"]
        assert template.uri_template == "resource://{param*}"
        assert template.name == "template_resource"


class TestPromptDecorator:
    async def test_prompt_decorator(self):
        mcp = FastMCP()

        @mcp.prompt
        def fn() -> str:
            return "Hello, world!"

        prompts_dict = await mcp.get_prompts()
        assert len(prompts_dict) == 1
        prompt = prompts_dict["fn"]
        assert prompt.name == "fn"
        # Don't compare functions directly since validate_call wraps them
        content = await prompt.render()
        assert content[0].content.text == "Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_without_parentheses(self):
        mcp = FastMCP()

        # This should now work correctly (not raise an error)
        @mcp.prompt  # No parentheses - this is now supported
        def fn() -> str:
            return "Hello, world!"

        # Verify the prompt was registered correctly
        prompts = await mcp.get_prompts()
        assert "fn" in prompts

        # Verify it can be called
        async with Client(mcp) as client:
            result = await client.get_prompt("fn")
            assert len(result.messages) == 1
            assert result.messages[0].content.text == "Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_with_name(self):
        mcp = FastMCP()

        @mcp.prompt(name="custom_name")
        def fn() -> str:
            return "Hello, world!"

        prompts_dict = await mcp.get_prompts()
        assert len(prompts_dict) == 1
        prompt = prompts_dict["custom_name"]
        assert prompt.name == "custom_name"
        content = await prompt.render()
        assert content[0].content.text == "Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_with_description(self):
        mcp = FastMCP()

        @mcp.prompt(description="A custom description")
        def fn() -> str:
            return "Hello, world!"

        prompts_dict = await mcp.get_prompts()
        assert len(prompts_dict) == 1
        prompt = prompts_dict["fn"]
        assert prompt.description == "A custom description"
        content = await prompt.render()
        assert content[0].content.text == "Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_with_parameters(self):
        mcp = FastMCP()

        @mcp.prompt
        def test_prompt(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

        prompts_dict = await mcp.get_prompts()
        assert len(prompts_dict) == 1
        prompt = prompts_dict["test_prompt"]
        assert prompt.arguments is not None
        assert len(prompt.arguments) == 2
        assert prompt.arguments[0].name == "name"
        assert prompt.arguments[0].required is True
        assert prompt.arguments[1].name == "greeting"
        assert prompt.arguments[1].required is False

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt", {"name": "World"})
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "Hello, World!"  # type: ignore[attr-defined]

            result = await client.get_prompt(
                "test_prompt", {"name": "World", "greeting": "Hi"}
            )
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "Hi, World!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_instance_method(self):
        mcp = FastMCP()

        class MyClass:
            def __init__(self, prefix: str):
                self.prefix = prefix

            def test_prompt(self) -> str:
                return f"{self.prefix} Hello, world!"

        obj = MyClass("My prefix:")
        mcp.add_prompt(Prompt.from_function(obj.test_prompt, name="test_prompt"))

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt")
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "My prefix: Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_classmethod(self):
        mcp = FastMCP()

        class MyClass:
            prefix = "Class prefix:"

            @classmethod
            def test_prompt(cls) -> str:
                return f"{cls.prefix} Hello, world!"

        mcp.add_prompt(Prompt.from_function(MyClass.test_prompt, name="test_prompt"))

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt")
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "Class prefix: Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_classmethod_error(self):
        mcp = FastMCP()

        with pytest.raises(ValueError, match="To decorate a classmethod"):

            class MyClass:
                @mcp.prompt
                @classmethod
                def test_prompt(cls) -> None:
                    pass

    async def test_prompt_decorator_staticmethod(self):
        mcp = FastMCP()

        class MyClass:
            @mcp.prompt
            @staticmethod
            def test_prompt() -> str:
                return "Static Hello, world!"

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt")
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "Static Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_async_function(self):
        mcp = FastMCP()

        @mcp.prompt
        async def test_prompt() -> str:
            return "Async Hello, world!"

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt")
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "Async Hello, world!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_with_tags(self):
        """Test that the prompt decorator properly sets tags."""
        mcp = FastMCP()

        @mcp.prompt(tags={"example", "test-tag"})
        def sample_prompt() -> str:
            return "Hello, world!"

        prompts_dict = await mcp.get_prompts()
        assert len(prompts_dict) == 1
        prompt = prompts_dict["sample_prompt"]
        assert prompt.tags == {"example", "test-tag"}

    async def test_prompt_decorator_with_string_name(self):
        """Test that @prompt(\"custom_name\") syntax works correctly."""
        mcp = FastMCP()

        @mcp.prompt("string_named_prompt")
        def my_function() -> str:
            """A function with a string name."""
            return "Hello from string named prompt!"

        # Verify the prompt was registered with the custom name
        prompts = await mcp.get_prompts()
        assert "string_named_prompt" in prompts
        assert "my_function" not in prompts  # Original name should not be registered

        # Verify it can be called
        async with Client(mcp) as client:
            result = await client.get_prompt("string_named_prompt")
            assert len(result.messages) == 1
            assert result.messages[0].content.text == "Hello from string named prompt!"  # type: ignore[attr-defined]

    async def test_prompt_direct_function_call(self):
        """Test that prompts can be registered via direct function call."""
        mcp = FastMCP()

        def standalone_function() -> str:
            """A standalone function to be registered."""
            return "Hello from direct call!"

        # Register it directly using the new syntax
        result_fn = mcp.prompt(standalone_function, name="direct_call_prompt")

        # The function should be returned unchanged
        assert isinstance(result_fn, FunctionPrompt)

        # Verify the prompt was registered correctly
        prompts = await mcp.get_prompts()
        assert prompts["direct_call_prompt"] is result_fn

        # Verify it can be called
        async with Client(mcp) as client:
            result = await client.get_prompt("direct_call_prompt")
            assert len(result.messages) == 1
            assert result.messages[0].content.text == "Hello from direct call!"  # type: ignore[attr-defined]

    async def test_prompt_decorator_conflicting_names_error(self):
        """Test that providing both positional and keyword names raises an error."""
        mcp = FastMCP()

        with pytest.raises(
            TypeError,
            match="Cannot specify both a name as first argument and as keyword argument",
        ):

            @mcp.prompt("positional_name", name="keyword_name")
            def my_function() -> str:
                return "Hello, world!"

    async def test_prompt_decorator_staticmethod_order(self):
        """Test that both decorator orders work for static methods"""
        mcp = FastMCP()

        class MyClass:
            @mcp.prompt  # type: ignore[misc]  # Type checker warns but runtime works
            @staticmethod
            def test_prompt() -> str:
                return "Static Hello, world!"

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt")
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.content.text == "Static Hello, world!"  # type: ignore[attr-defined]


class TestResourcePrefixHelpers:
    @pytest.mark.parametrize(
        "uri,prefix,expected",
        [
            # Normal paths
            (
                "resource://path/to/resource",
                "prefix",
                "resource://prefix/path/to/resource",
            ),
            # Absolute paths (with triple slash)
            ("resource:///absolute/path", "prefix", "resource://prefix//absolute/path"),
            # Empty prefix should return the original URI
            ("resource://path/to/resource", "", "resource://path/to/resource"),
            # Different protocols
            ("file://path/to/file", "prefix", "file://prefix/path/to/file"),
            ("http://example.com/path", "prefix", "http://prefix/example.com/path"),
            # Prefixes with special characters
            (
                "resource://path/to/resource",
                "pre.fix",
                "resource://pre.fix/path/to/resource",
            ),
            (
                "resource://path/to/resource",
                "pre/fix",
                "resource://pre/fix/path/to/resource",
            ),
            # Empty paths
            ("resource://", "prefix", "resource://prefix/"),
        ],
    )
    def test_add_resource_prefix(self, uri, prefix, expected):
        """Test that add_resource_prefix correctly adds prefixes to URIs."""
        result = add_resource_prefix(uri, prefix)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_uri",
        [
            "not-a-uri",
            "resource:no-slashes",
            "missing-protocol",
            "http:/missing-slash",
        ],
    )
    def test_add_resource_prefix_invalid_uri(self, invalid_uri):
        """Test that add_resource_prefix raises ValueError for invalid URIs."""
        with pytest.raises(ValueError, match="Invalid URI format"):
            add_resource_prefix(invalid_uri, "prefix")

    @pytest.mark.parametrize(
        "uri,prefix,expected",
        [
            # Normal paths
            (
                "resource://prefix/path/to/resource",
                "prefix",
                "resource://path/to/resource",
            ),
            # Absolute paths (with triple slash)
            ("resource://prefix//absolute/path", "prefix", "resource:///absolute/path"),
            # URI without the expected prefix should return the original URI
            (
                "resource://other/path/to/resource",
                "prefix",
                "resource://other/path/to/resource",
            ),
            # Empty prefix should return the original URI
            ("resource://path/to/resource", "", "resource://path/to/resource"),
            # Different protocols
            ("file://prefix/path/to/file", "prefix", "file://path/to/file"),
            # Prefixes with special characters (that need escaping in regex)
            (
                "resource://pre.fix/path/to/resource",
                "pre.fix",
                "resource://path/to/resource",
            ),
            (
                "resource://pre/fix/path/to/resource",
                "pre/fix",
                "resource://path/to/resource",
            ),
            # Empty paths
            ("resource://prefix/", "prefix", "resource://"),
        ],
    )
    def test_remove_resource_prefix(self, uri, prefix, expected):
        """Test that remove_resource_prefix correctly removes prefixes from URIs."""
        result = remove_resource_prefix(uri, prefix)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_uri",
        [
            "not-a-uri",
            "resource:no-slashes",
            "missing-protocol",
            "http:/missing-slash",
        ],
    )
    def test_remove_resource_prefix_invalid_uri(self, invalid_uri):
        """Test that remove_resource_prefix raises ValueError for invalid URIs."""
        with pytest.raises(ValueError, match="Invalid URI format"):
            remove_resource_prefix(invalid_uri, "prefix")

    @pytest.mark.parametrize(
        "uri,prefix,expected",
        [
            # URI with prefix
            ("resource://prefix/path/to/resource", "prefix", True),
            # URI with another prefix
            ("resource://other/path/to/resource", "prefix", False),
            # URI with prefix as a substring but not at path start
            ("resource://path/prefix/resource", "prefix", False),
            # Empty prefix
            ("resource://path/to/resource", "", False),
            # Different protocols
            ("file://prefix/path/to/file", "prefix", True),
            # Prefix with special characters
            ("resource://pre.fix/path/to/resource", "pre.fix", True),
            # Empty paths
            ("resource://prefix/", "prefix", True),
        ],
    )
    def test_has_resource_prefix(self, uri, prefix, expected):
        """Test that has_resource_prefix correctly identifies prefixes in URIs."""
        result = has_resource_prefix(uri, prefix)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_uri",
        [
            "not-a-uri",
            "resource:no-slashes",
            "missing-protocol",
            "http:/missing-slash",
        ],
    )
    def test_has_resource_prefix_invalid_uri(self, invalid_uri):
        """Test that has_resource_prefix raises ValueError for invalid URIs."""
        with pytest.raises(ValueError, match="Invalid URI format"):
            has_resource_prefix(invalid_uri, "prefix")


class TestResourcePrefixMounting:
    """Test resource prefixing in mounted servers."""

    async def test_mounted_server_resource_prefixing(self):
        """Test that resources in mounted servers use the correct prefix format."""
        # Create a server with resources
        server = FastMCP(name="ResourceServer")

        @server.resource("resource://test-resource")
        def get_resource():
            return "Resource content"

        @server.resource("resource:///absolute/path")
        def get_absolute_resource():
            return "Absolute resource content"

        @server.resource("resource://{param}/template")
        def get_template_resource(param: str):
            return f"Template resource with {param}"

        # Create a main server and mount the resource server
        main_server = FastMCP(name="MainServer")
        main_server.mount(server, "prefix")

        # Check that the resources are mounted with the correct prefixes
        resources = await main_server.get_resources()
        templates = await main_server.get_resource_templates()

        assert "resource://prefix/test-resource" in resources
        assert "resource://prefix//absolute/path" in resources
        assert "resource://prefix/{param}/template" in templates

        # Test that prefixed resources can be accessed
        async with Client(main_server) as client:
            # Regular resource
            result = await client.read_resource("resource://prefix/test-resource")
            assert result[0].text == "Resource content"  # type: ignore[attr-defined]

            # Absolute path resource
            result = await client.read_resource("resource://prefix//absolute/path")
            assert result[0].text == "Absolute resource content"  # type: ignore[attr-defined]

            # Template resource
            result = await client.read_resource(
                "resource://prefix/param-value/template"
            )
            assert result[0].text == "Template resource with param-value"  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "uri,prefix,expected_match,expected_strip",
        [
            # Regular resource
            (
                "resource://prefix/path/to/resource",
                "prefix",
                True,
                "resource://path/to/resource",
            ),
            # Absolute path
            (
                "resource://prefix//absolute/path",
                "prefix",
                True,
                "resource:///absolute/path",
            ),
            # Non-matching prefix
            (
                "resource://other/path/to/resource",
                "prefix",
                False,
                "resource://other/path/to/resource",
            ),
            # Different protocol
            ("http://prefix/example.com", "prefix", True, "http://example.com"),
        ],
    )
    async def test_mounted_server_matching_and_stripping(
        self, uri, prefix, expected_match, expected_strip
    ):
        """Test that resource prefix utility functions correctly match and strip resource prefixes."""
        from fastmcp.server.server import has_resource_prefix, remove_resource_prefix

        # Create a basic server to get the default resource prefix format
        server = FastMCP()

        # Test matching
        assert (
            has_resource_prefix(uri, prefix, server.resource_prefix_format)
            == expected_match
        )

        # Test stripping
        assert (
            remove_resource_prefix(uri, prefix, server.resource_prefix_format)
            == expected_strip
        )

    async def test_import_server_with_new_prefix_format(self):
        """Test that import_server correctly uses the new prefix format."""
        # Create a server with resources
        source_server = FastMCP(name="SourceServer")

        @source_server.resource("resource://test-resource")
        def get_resource():
            return "Resource content"

        @source_server.resource("resource:///absolute/path")
        def get_absolute_resource():
            return "Absolute resource content"

        @source_server.resource("resource://{param}/template")
        def get_template_resource(param: str):
            return f"Template resource with {param}"

        # Create target server and import the source server
        target_server = FastMCP(name="TargetServer")
        await target_server.import_server(source_server, "imported")

        # Check that the resources were imported with the correct prefixes
        resources = await target_server.get_resources()
        templates = await target_server.get_resource_templates()

        assert "resource://imported/test-resource" in resources
        assert "resource://imported//absolute/path" in resources
        assert "resource://imported/{param}/template" in templates

        # Verify we can access the resources
        async with Client(target_server) as client:
            result = await client.read_resource("resource://imported/test-resource")
            assert result[0].text == "Resource content"  # type: ignore[attr-defined]

            result = await client.read_resource("resource://imported//absolute/path")
            assert result[0].text == "Absolute resource content"  # type: ignore[attr-defined]

            result = await client.read_resource(
                "resource://imported/param-value/template"
            )
            assert result[0].text == "Template resource with param-value"  # type: ignore[attr-defined]


class TestShouldIncludeComponent:
    def test_no_filters_returns_true(self):
        """Test that when no include or exclude filters are provided, always returns True."""
        tool = Tool(name="test_tool", tags={"tag1", "tag2"}, parameters={})
        mcp = FastMCP(tools=[tool])
        result = mcp._should_enable_component(tool)
        assert result is True

    def test_exclude_string_tag_present_returns_false(self):
        """Test that when an exclude string tag is present in tags, returns False."""
        tool = Tool(
            name="test_tool", tags={"tag1", "tag2", "exclude_me"}, parameters={}
        )
        mcp = FastMCP(tools=[tool], exclude_tags={"exclude_me"})
        result = mcp._should_enable_component(tool)
        assert result is False

    def test_exclude_string_tag_absent_returns_true(self):
        """Test that when an exclude string tag is not present in tags, returns True."""
        tool = Tool(name="test_tool", tags={"tag1", "tag2"}, parameters={})
        mcp = FastMCP(tools=[tool], exclude_tags={"exclude_me"})
        result = mcp._should_enable_component(tool)
        assert result is True

    def test_multiple_exclude_tags_any_match_returns_false(self):
        """Test that when any exclude tag matches, returns False."""
        tool = Tool(name="test_tool", tags={"tag1", "tag2", "tag3"}, parameters={})
        mcp = FastMCP(
            tools=[tool], exclude_tags={"not_present", "tag2", "also_not_present"}
        )
        result = mcp._should_enable_component(tool)
        assert result is False

    def test_include_string_tag_present_returns_true(self):
        """Test that when an include string tag is present in tags, returns True."""
        tool = Tool(
            name="test_tool", tags={"tag1", "include_me", "tag2"}, parameters={}
        )
        mcp = FastMCP(tools=[tool], include_tags={"include_me"})
        result = mcp._should_enable_component(tool)
        assert result is True

    def test_include_string_tag_absent_returns_false(self):
        """Test that when an include string tag is not present in tags, returns False."""
        tool = Tool(name="test_tool", tags={"tag1", "tag2"}, parameters={})
        mcp = FastMCP(tools=[tool], include_tags={"include_me"})
        result = mcp._should_enable_component(tool)
        assert result is False

    def test_multiple_include_tags_any_match_returns_true(self):
        """Test that when any include tag matches, returns True."""
        tool = Tool(name="test_tool", tags={"tag1", "tag2", "tag3"}, parameters={})
        mcp = FastMCP(
            tools=[tool], include_tags={"not_present", "tag2", "also_not_present"}
        )
        result = mcp._should_enable_component(tool)
        assert result is True

    def test_multiple_include_tags_none_match_returns_false(self):
        """Test that when no include tags match, returns False."""
        tool = Tool(name="test_tool", tags={"tag1", "tag2", "tag3"}, parameters={})
        mcp = FastMCP(tools=[tool], include_tags={"not_present", "also_not_present"})
        result = mcp._should_enable_component(tool)
        assert result is False

    def test_exclude_takes_precedence_over_include(self):
        """Test that exclude tags take precedence over include tags."""
        tool = Tool(
            name="test_tool", tags={"tag1", "tag2", "exclude_me"}, parameters={}
        )
        mcp = FastMCP(tools=[tool], include_tags={"tag1"}, exclude_tags={"exclude_me"})
        result = mcp._should_enable_component(tool)
        assert result is False

    def test_empty_include_exclude_sets(self):
        """Test behavior with empty include/exclude sets."""
        # Empty include set means nothing matches
        tool1 = Tool(name="test_tool", tags={"tag1", "tag2"}, parameters={})
        mcp1 = FastMCP(tools=[tool1], include_tags=set())
        result = mcp1._should_enable_component(tool1)
        assert result is False

        # Empty exclude set means nothing excluded
        tool2 = Tool(name="test_tool", tags={"tag1", "tag2"}, parameters={})
        mcp2 = FastMCP(tools=[tool2], exclude_tags=set())
        result = mcp2._should_enable_component(tool2)
        assert result is True

    def test_empty_tags_with_filters(self):
        """Test behavior when input tags are empty."""
        # With include filters, empty tags should not match
        tool1 = Tool(name="test_tool", tags=set(), parameters={})
        mcp1 = FastMCP(tools=[tool1], include_tags={"required_tag"})
        result = mcp1._should_enable_component(tool1)
        assert result is False

        # With exclude filters but no include, empty tags should pass
        tool2 = Tool(name="test_tool", tags=set(), parameters={})
        mcp2 = FastMCP(tools=[tool2], exclude_tags={"bad_tag"})
        result = mcp2._should_enable_component(tool2)
        assert result is True


class TestMetadataServer:
    """Tests for the metadata server functionality."""

    async def test_get_metadata_basic(self):
        """Test that get_metadata returns basic metadata structure."""
        mcp = FastMCP(name="TestServer", instructions="Test instructions")
        
        @mcp.tool
        def test_tool(x: int) -> int:
            return x + 1
        
        @mcp.resource("resource://test")
        def test_resource() -> str:
            return "test data"
        
        @mcp.prompt
        def test_prompt() -> str:
            return "test prompt"
        
        metadata = mcp.get_metadata()
        
        assert metadata["name"] == "TestServer"
        assert metadata["instructions"] == "Test instructions"
        assert metadata["version"] == "1.0.0"
        
        assert metadata["capabilities"]["tools"] == 1
        assert metadata["capabilities"]["resources"] == 1
        assert metadata["capabilities"]["prompts"] == 1
        
        assert len(metadata["schemas"]["tools"]) == 1
        assert len(metadata["schemas"]["resources"]) == 1
        assert len(metadata["schemas"]["prompts"]) == 1
        
        assert "server_capabilities" in metadata
        assert metadata["server_capabilities"]["experimental"]["http_metadata"] is True

    async def test_get_metadata_with_oauth2(self):
        """Test that get_metadata includes OAuth2 configuration when present."""
        mcp = FastMCP(name="TestServer")
        
        # Set OAuth2 config
        mcp._oauth_config = {
            "base_url": "https://example.com",
            "dynamic_registration": True,
            "scopes_supported": ["read", "write"]
        }
        
        metadata = mcp.get_metadata()
        
        assert "oauth2" in metadata
        oauth2 = metadata["oauth2"]
        assert oauth2["authorization_endpoint"] == "https://example.com/oauth/authorize"
        assert oauth2["token_endpoint"] == "https://example.com/oauth/token"
        assert oauth2["jwks_uri"] == "https://example.com/oauth/jwks"
        assert oauth2["scopes_supported"] == ["read", "write"]
        assert oauth2["registration_endpoint"] == "https://example.com/oauth/register"
        
        # Check server capabilities
        assert metadata["server_capabilities"]["experimental"]["oauth2_dynamic_registration"] is True

    async def test_get_metadata_without_oauth2(self):
        """Test that get_metadata works without OAuth2 configuration."""
        mcp = FastMCP(name="TestServer")
        
        metadata = mcp.get_metadata()
        
        assert "oauth2" not in metadata
        assert metadata["server_capabilities"]["experimental"]["oauth2_dynamic_registration"] is False

    async def test_metadata_server_lifecycle(self):
        """Test starting and stopping the metadata server."""
        mcp = FastMCP(name="TestServer")
        
        # Should not be running initially
        assert not hasattr(mcp, '_metadata_server') or mcp._metadata_server is None
        
        # Start server
        mcp.start_metadata_server(port=8081)
        
        # Should be running
        assert hasattr(mcp, '_metadata_server') and mcp._metadata_server is not None
        assert hasattr(mcp, '_metadata_thread') and mcp._metadata_thread is not None
        
        # Stop server
        mcp.stop_metadata_server()
        
        # Should be stopped
        assert mcp._metadata_server is None

    async def test_metadata_server_already_running_error(self):
        """Test that starting metadata server twice raises an error."""
        mcp = FastMCP(name="TestServer")
        
        mcp.start_metadata_server(port=8082)
        
        with pytest.raises(RuntimeError, match="Metadata server is already running"):
            mcp.start_metadata_server(port=8083)
        
        mcp.stop_metadata_server()

    async def test_metadata_server_with_oauth_config(self):
        """Test metadata server with OAuth2 configuration."""
        mcp = FastMCP(name="TestServer")
        
        oauth_config = {
            "dynamic_registration": True,
            "scopes_supported": ["read", "write", "admin"],
            "jwks_keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key",
                    "use": "sig",
                    "alg": "RS256",
                    "n": "test-modulus",
                    "e": "AQAB"
                }
            ]
        }
        
        mcp.start_metadata_server(port=8084, oauth_config=oauth_config)
        
        # Check that OAuth config was stored
        assert mcp._oauth_config == oauth_config
        assert mcp._oauth_config["base_url"] == "http://localhost:8084"
        
        # Check that OAuth storage was initialized
        assert mcp._oauth_storage is not None
        
        mcp.stop_metadata_server()

    async def test_metadata_sanitization(self):
        """Test that metadata response is properly sanitized."""
        mcp = FastMCP(name="TestServer")
        
        # Test with minimal valid metadata
        metadata = mcp.get_metadata()
        
        # Should not raise any validation errors
        assert "name" in metadata
        assert "capabilities" in metadata
        assert "schemas" in metadata
        
        # Test with OAuth2 config
        mcp._oauth_config = {
            "base_url": "https://example.com",
            "scopes_supported": ["read"]
        }
        
        metadata = mcp.get_metadata()
        
        # Should have valid OAuth2 configuration
        assert metadata["oauth2"]["authorization_endpoint"] == "https://example.com/oauth/authorize"
        assert metadata["oauth2"]["token_endpoint"] == "https://example.com/oauth/token"
        assert metadata["oauth2"]["jwks_uri"] == "https://example.com/oauth/jwks"

    async def test_metadata_response_schema_validation(self):
        """Test that metadata response contains all required schemas."""
        mcp = FastMCP(name="TestServer")
        
        @mcp.tool
        def tool_with_schema(x: int, y: str = "default") -> bool:
            """A tool with a schema."""
            return x > 0
        
        @mcp.resource("resource://test", description="Test resource")
        def resource_with_meta() -> str:
            return "data"
        
        @mcp.resource("resource://{param}", description="Test template")
        def template_with_meta(param: str) -> str:
            return f"data-{param}"
        
        @mcp.prompt
        def prompt_with_args(name: str, greeting: str = "Hello") -> str:
            """A prompt with arguments."""
            return f"{greeting}, {name}!"
        
        metadata = mcp.get_metadata()
        
        # Check tool schema
        tool_schema = metadata["schemas"]["tools"][0]
        assert tool_schema["name"] == "tool_with_schema"
        assert tool_schema["description"] == "A tool with a schema."
        assert tool_schema["tags"] == []
        assert "input_schema" in tool_schema
        
        # Check resource schema
        resource_schema = metadata["schemas"]["resources"][0]
        assert resource_schema["uri"] == "resource://test"
        assert resource_schema["name"] == "resource_with_meta"
        assert resource_schema["description"] == "Test resource"
        assert resource_schema["tags"] == []
        
        # Check template schema
        template_schema = metadata["schemas"]["resource_templates"][0]
        assert template_schema["uri_template"] == "resource://{param}"
        assert template_schema["name"] == "template_with_meta"
        assert template_schema["description"] == "Test template"
        
        # Check prompt schema
        prompt_schema = metadata["schemas"]["prompts"][0]
        assert prompt_schema["name"] == "prompt_with_args"
        assert prompt_schema["description"] == "A prompt with arguments."
        assert "arguments" in prompt_schema

    async def test_metadata_with_tags(self):
        """Test that metadata includes tag information."""
        mcp = FastMCP(name="TestServer")
        
        @mcp.tool(tags={"math", "utility"})
        def tagged_tool(x: int) -> int:
            return x + 1
        
        @mcp.resource("resource://tagged", tags={"data", "test"})
        def tagged_resource() -> str:
            return "tagged data"
        
        @mcp.prompt(tags={"ai", "assistant"})
        def tagged_prompt() -> str:
            return "tagged prompt"
        
        metadata = mcp.get_metadata()
        
        # Check that tags are included in schemas
        tool_schema = metadata["schemas"]["tools"][0]
        assert set(tool_schema["tags"]) == {"math", "utility"}
        
        resource_schema = metadata["schemas"]["resources"][0]
        assert set(resource_schema["tags"]) == {"data", "test"}
        
        prompt_schema = metadata["schemas"]["prompts"][0]
        assert set(prompt_schema["tags"]) == {"ai", "assistant"}


class TestOAuth2Storage:
    """Tests for the OAuth2Storage class."""

    def test_oauth2_storage_init(self):
        """Test OAuth2Storage initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            storage = OAuth2Storage(str(db_path))
            
            # Check that database file was created
            assert db_path.exists()
            
            # Check that tables were created
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                assert "oauth_clients" in tables
                assert "oauth_tokens" in tables
                assert "oauth_auth_codes" in tables

    def test_client_registration(self):
        """Test client registration functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            storage = OAuth2Storage(str(db_path))
            
            client_data = {
                "client_name": "Test Client",
                "redirect_uris": ["https://example.com/callback"],
                "grant_types": ["authorization_code", "client_credentials"],
                "scopes": ["read", "write"]
            }
            
            result = storage.register_client(client_data)
            
            # Check response structure
            assert "client_id" in result
            assert "client_secret" in result
            assert result["client_name"] == "Test Client"
            assert result["redirect_uris"] == ["https://example.com/callback"]
            assert result["grant_types"] == ["authorization_code", "client_credentials"]
            assert result["scopes"] == ["read", "write"]
            
            # Check that client was stored in database
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM oauth_clients")
                count = cursor.fetchone()[0]
                assert count == 1

    def test_client_credential_validation(self):
        """Test client credential validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            storage = OAuth2Storage(str(db_path))
            
            # Register a client
            client_data = {
                "client_name": "Test Client",
                "grant_types": ["client_credentials"]
            }
            result = storage.register_client(client_data)
            client_id = result["client_id"]
            client_secret = result["client_secret"]
            
            # Test valid credentials
            client_info = storage.validate_client_credentials(client_id, client_secret)
            assert client_info is not None
            assert client_info["client_id"] == client_id
            assert client_info["client_name"] == "Test Client"
            
            # Test invalid credentials
            invalid_info = storage.validate_client_credentials(client_id, "wrong_secret")
            assert invalid_info is None
            
            # Test non-existent client
            invalid_info = storage.validate_client_credentials("fake_client", client_secret)
            assert invalid_info is None

    def test_access_token_storage_and_validation(self):
        """Test access token storage and validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            storage = OAuth2Storage(str(db_path))
            
            # Register a client first
            client_data = {"client_name": "Test Client"}
            result = storage.register_client(client_data)
            client_id = result["client_id"]
            
            # Store an access token
            access_token = "test_access_token"
            scopes = ["read", "write"]
            token_id = storage.store_access_token(client_id, access_token, 3600, scopes)
            
            assert token_id is not None
            
            # Validate the token
            token_info = storage.validate_access_token(access_token)
            assert token_info is not None
            assert token_info["client_id"] == client_id
            assert token_info["scopes"] == scopes
            
            # Test invalid token
            invalid_info = storage.validate_access_token("invalid_token")
            assert invalid_info is None

    def test_authorization_code_storage_and_validation(self):
        """Test authorization code storage and validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            storage = OAuth2Storage(str(db_path))
            
            # Register a client first
            client_data = {"client_name": "Test Client"}
            result = storage.register_client(client_data)
            client_id = result["client_id"]
            
            # Store an authorization code
            redirect_uri = "https://example.com/callback"
            scopes = ["read"]
            auth_code = storage.store_authorization_code(client_id, redirect_uri, scopes)
            
            assert auth_code is not None
            
            # Validate the code
            code_info = storage.validate_authorization_code(auth_code, client_id, redirect_uri)
            assert code_info is not None
            assert code_info["client_id"] == client_id
            assert code_info["redirect_uri"] == redirect_uri
            assert code_info["scopes"] == scopes
            
            # Test that code can't be used twice
            invalid_info = storage.validate_authorization_code(auth_code, client_id, redirect_uri)
            assert invalid_info is None

    def test_cleanup_expired_tokens(self):
        """Test cleanup of expired tokens and codes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            storage = OAuth2Storage(str(db_path))
            
            # Register a client
            client_data = {"client_name": "Test Client"}
            result = storage.register_client(client_data)
            client_id = result["client_id"]
            
            # Store an expired token (expires in -1 seconds)
            storage.store_access_token(client_id, "expired_token", -1, ["read"])
            
            # Store an expired auth code
            storage.store_authorization_code(client_id, "https://example.com", ["read"], -1)
            
            # Run cleanup
            storage.cleanup_expired_tokens()
            
            # Check that expired items were removed
            token_info = storage.validate_access_token("expired_token")
            assert token_info is None


class TestOAuth2Endpoints:
    """Tests for OAuth2 endpoint functionality."""

    async def test_jwks_fetcher_caching(self):
        """Test JWKS fetcher caching mechanism."""
        from fastmcp.server.server import _fetch_jwks, _jwks
        
        # Mock httpx.get to return test data
        test_jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key",
                    "use": "sig",
                    "alg": "RS256",
                    "n": "test-modulus",
                    "e": "AQAB"
                }
            ]
        }
        
        with patch("httpx.get") as mock_get:
            mock_response = mock_get.return_value
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = test_jwks
            
            # First call should fetch from network
            keys1 = _jwks("https://example.com")
            assert len(keys1) == 1
            assert keys1[0]["kid"] == "test-key"
            assert mock_get.call_count == 1
            
            # Second call should use cache
            keys2 = _jwks("https://example.com")
            assert keys2 == keys1
            assert mock_get.call_count == 1  # Should not increase
            
            # Clear cache and verify it refetches
            _fetch_jwks.cache_clear()
            keys3 = _jwks("https://example.com")
            assert keys3 == keys1
            assert mock_get.call_count == 2  # Should increase

    async def test_jwks_fetcher_descope_url(self):
        """Test JWKS fetcher with Descope-specific URL handling."""
        from fastmcp.server.server import _fetch_jwks
        
        with patch("httpx.get") as mock_get:
            mock_response = mock_get.return_value
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"keys": []}
            
            # Test Descope URL transformation
            _fetch_jwks("https://api.descope.com/v1/apps/test-project")
            
            # Check that the URL was transformed correctly
            expected_url = "https://api.descope.com/test-project/.well-known/jwks.json"
            mock_get.assert_called_with(expected_url, timeout=5)

    async def test_metadata_response_sanitization(self):
        """Test metadata response sanitization functions."""
        from fastmcp.server.server import _sanitize_metadata_response, _sanitize_oauth_metadata
        
        # Test valid metadata
        valid_metadata = {
            "name": "TestServer",
            "capabilities": {"tools": 1},
            "schemas": {"tools": []}
        }
        
        result = _sanitize_metadata_response(valid_metadata)
        assert result == valid_metadata
        
        # Test invalid metadata - missing required field
        invalid_metadata = {
            "name": "TestServer",
            "capabilities": {"tools": 1}
            # Missing "schemas"
        }
        
        with pytest.raises(ValueError, match="Missing required field: schemas"):
            _sanitize_metadata_response(invalid_metadata)
        
        # Test valid OAuth2 metadata
        valid_oauth = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/oauth/authorize",
            "token_endpoint": "https://example.com/oauth/token"
        }
        
        result = _sanitize_oauth_metadata(valid_oauth)
        assert result == valid_oauth
        
        # Test invalid OAuth2 metadata
        invalid_oauth = {
            "issuer": "https://example.com",
            "authorization_endpoint": "invalid-url",
            "token_endpoint": "https://example.com/oauth/token" 
        }
        
        with pytest.raises(ValueError, match="Invalid URL"):
            _sanitize_oauth_metadata(invalid_oauth)

    async def test_client_credentials_parsing(self):
        """Test client credentials parsing from different sources."""
        from fastmcp.server.server import _parse_client_credentials
        import base64
        
        # Test Basic authentication
        credentials = base64.b64encode(b"client_id:client_secret").decode()
        headers = {"Authorization": f"Basic {credentials}"}
        form_data = {}
        
        client_id, client_secret = _parse_client_credentials(headers, form_data)
        assert client_id == "client_id"
        assert client_secret == "client_secret"
        
        # Test form data
        headers = {}
        form_data = {"client_id": "form_client", "client_secret": "form_secret"}
        
        client_id, client_secret = _parse_client_credentials(headers, form_data)
        assert client_id == "form_client"
        assert client_secret == "form_secret"
        
        # Test Basic auth takes precedence
        headers = {"Authorization": f"Basic {credentials}"}
        form_data = {"client_id": "form_client", "client_secret": "form_secret"}
        
        client_id, client_secret = _parse_client_credentials(headers, form_data)
        assert client_id == "client_id"  
        assert client_secret == "client_secret" 
        
        # Test invalid Basic auth
        headers = {"Authorization": "Basic invalid_base64"}
        form_data = {"client_id": "form_client", "client_secret": "form_secret"}
        
        client_id, client_secret = _parse_client_credentials(headers, form_data)
        assert client_id == "form_client"  
        assert client_secret == "form_secret"


class TestOAuth2Integration:
    """Integration tests for OAuth2 functionality."""

    async def test_full_oauth2_flow(self):
        """Test complete OAuth2 flow with FastMCP server."""
        mcp = FastMCP(name="OAuth2TestServer")
        
        @mcp.tool
        def secure_operation(data: str) -> str:
            return f"Processed: {data}"
        
        # Configure OAuth2
        oauth_config = {
            "dynamic_registration": True,
            "scopes_supported": ["read", "write"],
            "jwks_keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key",
                    "use": "sig",
                    "alg": "RS256",
                    "n": "test-modulus",
                    "e": "AQAB"
                }
            ]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "oauth2.db"
            
            mcp.start_metadata_server(
                port=8085,
                oauth_config=oauth_config,
                oauth_db_path=str(db_path)
            )
            
            try:
                assert mcp._oauth_storage is not None
                
                # Test client registration
                client_data = {
                    "client_name": "Integration Test Client",
                    "grant_types": ["client_credentials"]
                }
                
                registered_client = mcp._oauth_storage.register_client(client_data)
                assert registered_client["client_id"] is not None
                assert registered_client["client_secret"] is not None
                
                # Test credential validation
                client_info = mcp._oauth_storage.validate_client_credentials(
                    registered_client["client_id"],
                    registered_client["client_secret"]
                )
                assert client_info is not None
                assert client_info["client_name"] == "Integration Test Client"
                
                # Test token generation
                access_token = "test_token"
                token_id = mcp._oauth_storage.store_access_token(
                    registered_client["client_id"],
                    access_token,
                    3600,
                    ["read", "write"]
                )
                assert token_id is not None
                
                # Test token validation
                token_info = mcp._oauth_storage.validate_access_token(access_token)
                assert token_info is not None
                assert token_info["client_id"] == registered_client["client_id"]
                
            finally:
                mcp.stop_metadata_server()

    async def test_oauth2_metadata_includes_all_endpoints(self):
        """Test that OAuth2 metadata includes all required endpoints."""
        mcp = FastMCP(name="OAuth2TestServer")
        
        oauth_config = {
            "dynamic_registration": True,
            "scopes_supported": ["read", "write", "admin"]
        }
        
        # Set OAuth2 config
        mcp._oauth_config = oauth_config
        mcp._oauth_config["base_url"] = "https://test.example.com"
        
        metadata = mcp.get_metadata()
        
        assert "oauth2" in metadata
        oauth2 = metadata["oauth2"]
        
        assert oauth2["authorization_endpoint"] == "https://test.example.com/oauth/authorize"
        assert oauth2["token_endpoint"] == "https://test.example.com/oauth/token"
        assert oauth2["jwks_uri"] == "https://test.example.com/oauth/jwks"
        
        assert oauth2["registration_endpoint"] == "https://test.example.com/oauth/register"
        
        assert oauth2["scopes_supported"] == ["read", "write", "admin"]
        assert "code" in oauth2["response_types_supported"]
        assert "authorization_code" in oauth2["grant_types_supported"]
        assert "client_credentials" in oauth2["grant_types_supported"]
        assert "S256" in oauth2["code_challenge_methods_supported"]
        assert "client_secret_basic" in oauth2["token_endpoint_auth_methods_supported"]
        assert "client_secret_post" in oauth2["token_endpoint_auth_methods_supported"]

    async def test_oauth2_without_dynamic_registration(self):
        """Test OAuth2 configuration without dynamic registration."""
        mcp = FastMCP(name="OAuth2TestServer")
        
        oauth_config = {
            "dynamic_registration": False,
            "scopes_supported": ["read"]
        }
        
        mcp._oauth_config = oauth_config
        mcp._oauth_config["base_url"] = "https://test.example.com"
        
        metadata = mcp.get_metadata()
        
        assert "oauth2" in metadata
        oauth2 = metadata["oauth2"]
        
        assert "registration_endpoint" not in oauth2
        
        assert "authorization_endpoint" in oauth2
        assert "token_endpoint" in oauth2
        assert "jwks_uri" in oauth2
        
        assert metadata["server_capabilities"]["experimental"]["oauth2_dynamic_registration"] is False