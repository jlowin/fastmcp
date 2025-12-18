"""Test dead proxy with shared prefix scenarios.

These tests verify that when a dead proxy and a working server share the same
prefix (or have no prefix), the system gracefully falls back to the working
server instead of failing.
"""

from fastmcp import Client, FastMCP
from fastmcp.client.transports import SSETransport


class TestDeadProxySharedPrefix:
    """Test graceful handling when dead proxy shares prefix with working server."""

    async def test_dead_proxy_first_same_prefix_tools(self):
        """Test tool call when dead proxy is mounted FIRST with same prefix."""
        main_app = FastMCP("MainApp")
        working_app = FastMCP("WorkingApp")

        @working_app.tool
        def my_tool() -> str:
            return "Working tool"

        # Mount unreachable proxy FIRST with prefix "shared"
        unreachable_client = Client(
            transport=SSETransport("http://127.0.0.1:9999/sse/"),
            name="unreachable_client",
        )
        unreachable_proxy = FastMCP.as_proxy(
            unreachable_client, name="unreachable_proxy"
        )
        main_app.mount(unreachable_proxy, "shared")

        # Mount working server SECOND with SAME prefix "shared"
        main_app.mount(working_app, "shared")

        async with Client(main_app) as client:
            # List should work (errors caught)
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "shared_my_tool" in tool_names

            # Call the tool - should fall back to working server
            result = await client.call_tool("shared_my_tool", {})
            assert result.data == "Working tool"

    async def test_dead_proxy_first_no_prefix_tools(self):
        """Test tool call when dead proxy is mounted FIRST with no prefix."""
        main_app = FastMCP("MainApp")
        working_app = FastMCP("WorkingApp")

        @working_app.tool
        def my_tool() -> str:
            return "Working tool"

        # Mount unreachable proxy FIRST without prefix
        unreachable_client = Client(
            transport=SSETransport("http://127.0.0.1:9999/sse/"),
            name="unreachable_client",
        )
        unreachable_proxy = FastMCP.as_proxy(
            unreachable_client, name="unreachable_proxy"
        )
        main_app.mount(unreachable_proxy)

        # Mount working server SECOND without prefix
        main_app.mount(working_app)

        async with Client(main_app) as client:
            # List should work (errors caught)
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "my_tool" in tool_names

            # Call the tool - should fall back to working server
            result = await client.call_tool("my_tool", {})
            assert result.data == "Working tool"

    async def test_dead_proxy_first_same_prefix_resources(self):
        """Test resource read when dead proxy is mounted FIRST with same prefix."""
        main_app = FastMCP("MainApp")
        working_app = FastMCP("WorkingApp")

        @working_app.resource(uri="data://info")
        def my_resource() -> str:
            return "Working resource"

        # Mount unreachable proxy FIRST
        unreachable_client = Client(
            transport=SSETransport("http://127.0.0.1:9999/sse/"),
            name="unreachable_client",
        )
        unreachable_proxy = FastMCP.as_proxy(
            unreachable_client, name="unreachable_proxy"
        )
        main_app.mount(unreachable_proxy, "shared")

        # Mount working server SECOND with same prefix
        main_app.mount(working_app, "shared")

        async with Client(main_app) as client:
            # List should work
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]
            assert "data://shared/info" in resource_uris

            # Read resource - should fall back to working server
            result = await client.read_resource("data://shared/info")
            assert result[0].text == "Working resource"

    async def test_dead_proxy_first_same_prefix_prompts(self):
        """Test prompt render when dead proxy is mounted FIRST with same prefix."""
        main_app = FastMCP("MainApp")
        working_app = FastMCP("WorkingApp")

        @working_app.prompt
        def my_prompt() -> str:
            return "Working prompt"

        # Mount unreachable proxy FIRST
        unreachable_client = Client(
            transport=SSETransport("http://127.0.0.1:9999/sse/"),
            name="unreachable_client",
        )
        unreachable_proxy = FastMCP.as_proxy(
            unreachable_client, name="unreachable_proxy"
        )
        main_app.mount(unreachable_proxy, "shared")

        # Mount working server SECOND with same prefix
        main_app.mount(working_app, "shared")

        async with Client(main_app) as client:
            # List should work
            prompts = await client.list_prompts()
            prompt_names = [p.name for p in prompts]
            assert "shared_my_prompt" in prompt_names

            # Get prompt - should fall back to working server
            result = await client.get_prompt("shared_my_prompt")
            assert result.messages[0].content.text == "Working prompt"

    async def test_dead_proxy_first_no_prefix_resources(self):
        """Test resource read when dead proxy is mounted FIRST with no prefix."""
        main_app = FastMCP("MainApp")
        working_app = FastMCP("WorkingApp")

        @working_app.resource(uri="data://info")
        def my_resource() -> str:
            return "Working resource"

        # Mount unreachable proxy FIRST without prefix
        unreachable_client = Client(
            transport=SSETransport("http://127.0.0.1:9999/sse/"),
            name="unreachable_client",
        )
        unreachable_proxy = FastMCP.as_proxy(
            unreachable_client, name="unreachable_proxy"
        )
        main_app.mount(unreachable_proxy)

        # Mount working server SECOND without prefix
        main_app.mount(working_app)

        async with Client(main_app) as client:
            # List should work
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]
            assert "data://info" in resource_uris

            # Read resource - should fall back to working server
            result = await client.read_resource("data://info")
            assert result[0].text == "Working resource"

    async def test_dead_proxy_first_no_prefix_prompts(self):
        """Test prompt render when dead proxy is mounted FIRST with no prefix."""
        main_app = FastMCP("MainApp")
        working_app = FastMCP("WorkingApp")

        @working_app.prompt
        def my_prompt() -> str:
            return "Working prompt"

        # Mount unreachable proxy FIRST without prefix
        unreachable_client = Client(
            transport=SSETransport("http://127.0.0.1:9999/sse/"),
            name="unreachable_client",
        )
        unreachable_proxy = FastMCP.as_proxy(
            unreachable_client, name="unreachable_proxy"
        )
        main_app.mount(unreachable_proxy)

        # Mount working server SECOND without prefix
        main_app.mount(working_app)

        async with Client(main_app) as client:
            # List should work
            prompts = await client.list_prompts()
            prompt_names = [p.name for p in prompts]
            assert "my_prompt" in prompt_names

            # Get prompt - should fall back to working server
            result = await client.get_prompt("my_prompt")
            assert result.messages[0].content.text == "Working prompt"
