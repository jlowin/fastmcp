from __future__ import annotations

import pytest

from fastmcp import Client, FastMCP

pytestmark = pytest.mark.core


class TestServerCreation:
    def test_create_server_with_defaults(self) -> None:
        mcp = FastMCP()
        assert mcp.name.startswith("FastMCP-")

    def test_create_server_with_name(self) -> None:
        mcp = FastMCP(name="TestServer")
        assert mcp.name == "TestServer"

    def test_create_server_with_instructions(self) -> None:
        mcp = FastMCP(instructions="Test instructions")
        assert mcp.instructions == "Test instructions"

    def test_modify_instructions(self) -> None:
        mcp = FastMCP(instructions="Initial")
        mcp.instructions = "Updated"
        assert mcp.instructions == "Updated"


class TestToolRegistration:
    def test_register_tool_with_decorator(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        assert greet("World") == "Hello, World!"

    def test_register_tool_with_custom_name(self) -> None:
        mcp = FastMCP()

        @mcp.tool(name="custom_greet")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        assert greet("World") == "Hello, World!"

    def test_register_async_tool(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        async def async_greet(name: str) -> str:
            return f"Hello, {name}!"

        import asyncio

        result = asyncio.run(async_greet("World"))
        assert result == "Hello, World!"

    def test_register_multiple_tools(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def add(a: int, b: int) -> int:
            return a + b

        @mcp.tool
        def multiply(a: int, b: int) -> int:
            return a * b

        assert add(2, 3) == 5
        assert multiply(2, 3) == 6


class TestResourceRegistration:
    def test_register_resource_with_decorator(self) -> None:
        mcp = FastMCP()

        @mcp.resource(uri="data://config")
        def get_config() -> str:
            return '{"key": "value"}'

        assert get_config() == '{"key": "value"}'

    def test_register_resource_template(self) -> None:
        mcp = FastMCP()

        @mcp.resource(uri="data://user/{user_id}")
        def get_user(user_id: str) -> str:
            return f'{{"id": "{user_id}"}}'

        assert get_user("123") == '{"id": "123"}'


class TestPromptRegistration:
    def test_register_prompt_with_decorator(self) -> None:
        mcp = FastMCP()

        @mcp.prompt
        def welcome(name: str) -> str:
            return f"Welcome, {name}!"

        assert welcome("User") == "Welcome, User!"

    def test_register_prompt_with_custom_name(self) -> None:
        mcp = FastMCP()

        @mcp.prompt(name="custom_welcome")
        def welcome(name: str) -> str:
            return f"Welcome, {name}!"

        assert welcome("User") == "Welcome, User!"


class TestClientServerIntegration:
    async def test_list_tools_via_client(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0].name == "greet"

    async def test_call_tool_via_client(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def add(a: int, b: int) -> int:
            return a + b

        async with Client(mcp) as client:
            result = await client.call_tool("add", {"a": 5, "b": 3})
            assert result.data == 8

    async def test_call_tool_with_string_result(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        async with Client(mcp) as client:
            result = await client.call_tool("greet", {"name": "World"})
            assert result.data == "Hello, World!"

    async def test_list_resources_via_client(self) -> None:
        mcp = FastMCP()

        @mcp.resource(uri="data://config")
        def get_config() -> str:
            return '{"setting": "value"}'

        async with Client(mcp) as client:
            resources = await client.list_resources()
            assert len(resources) == 1
            assert str(resources[0].uri) == "data://config"

    async def test_read_resource_via_client(self) -> None:
        mcp = FastMCP()

        @mcp.resource(uri="data://config")
        def get_config() -> str:
            return '{"setting": "value"}'

        async with Client(mcp) as client:
            contents = await client.read_resource("data://config")
            assert len(contents) == 1
            assert contents[0].text == '{"setting": "value"}'

    async def test_list_prompts_via_client(self) -> None:
        mcp = FastMCP()

        @mcp.prompt
        def welcome(name: str) -> str:
            return f"Welcome, {name}!"

        async with Client(mcp) as client:
            prompts = await client.list_prompts()
            assert len(prompts) == 1
            assert prompts[0].name == "welcome"

    async def test_get_prompt_via_client(self) -> None:
        mcp = FastMCP()

        @mcp.prompt
        def welcome(name: str) -> str:
            return f"Welcome, {name}!"

        async with Client(mcp) as client:
            result = await client.get_prompt("welcome", {"name": "User"})
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.role == "user"


class TestToolErrorHandling:
    async def test_tool_raises_exception(self) -> None:
        from fastmcp.exceptions import ToolError

        mcp = FastMCP()

        @mcp.tool
        def failing_tool() -> str:
            raise ValueError("Something went wrong")

        async with Client(mcp) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("failing_tool", {})
            assert "Something went wrong" in str(exc_info.value)

    async def test_call_nonexistent_tool(self) -> None:
        mcp = FastMCP()

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("nonexistent", {})


class TestStandaloneToolDecorator:
    def test_standalone_tool_decorator(self) -> None:
        from fastmcp.tools import tool

        @tool
        def standalone_greet(name: str) -> str:
            return f"Hello, {name}!"

        assert standalone_greet("World") == "Hello, World!"
        assert hasattr(standalone_greet, "__fastmcp__")

    def test_standalone_tool_with_name(self) -> None:
        from fastmcp.tools import tool

        @tool(name="custom_name")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        assert greet("World") == "Hello, World!"
        assert greet.__fastmcp__.name == "custom_name"


class TestNonAsciiContent:
    async def test_unicode_in_tool_description(self) -> None:
        mcp = FastMCP()

        @mcp.tool(description="Tool with émojis 🎉 and ünïcödë")
        def unicode_tool() -> str:
            return "Success!"

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 1
            assert "🎉" in (tools[0].description or "")

    async def test_unicode_in_tool_arguments(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        async with Client(mcp) as client:
            result = await client.call_tool("greet", {"name": "世界"})
            assert result.data == "Hello, 世界!"

    async def test_unicode_in_tool_return(self) -> None:
        mcp = FastMCP()

        @mcp.tool
        def get_greeting() -> str:
            return "¡Hola, Mundo! 👋"

        async with Client(mcp) as client:
            result = await client.call_tool("get_greeting", {})
            assert result.data == "¡Hola, Mundo! 👋"
