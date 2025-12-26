from fastmcp import Client, FastMCP
from fastmcp.utilities.tests import temporary_settings


class TestMeta:
    """Test that include_fastmcp_meta controls whether _fastmcp key is present in meta."""

    async def test_tool_tags_in_meta_with_default_setting(self):
        """Test that tool tags appear in meta under _fastmcp key with default setting."""
        mcp = FastMCP()

        @mcp.tool(tags={"tool-example", "test-tool-tag"})
        def sample_tool(x: int) -> int:
            """A sample tool."""
            return x * 2

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "sample_tool")
            assert tool.meta is not None
            assert set(tool.meta["_fastmcp"]["tags"]) == {
                "tool-example",
                "test-tool-tag",
            }

    async def test_resource_tags_in_meta_with_default_setting(self):
        """Test that resource tags appear in meta under _fastmcp key with default setting."""
        mcp = FastMCP()

        @mcp.resource(
            uri="test://resource", tags={"resource-example", "test-resource-tag"}
        )
        def sample_resource() -> str:
            """A sample resource."""
            return "resource content"

        async with Client(mcp) as client:
            resources = await client.list_resources()
            resource = next(r for r in resources if str(r.uri) == "test://resource")
            assert resource.meta is not None
            assert set(resource.meta["_fastmcp"]["tags"]) == {
                "resource-example",
                "test-resource-tag",
            }

    async def test_resource_template_tags_in_meta_with_default_setting(self):
        """Test that resource template tags appear in meta under _fastmcp key with default setting."""
        mcp = FastMCP()

        @mcp.resource(
            "test://template/{id}", tags={"template-example", "test-template-tag"}
        )
        def sample_template(id: str) -> str:
            """A sample resource template."""
            return f"template content for {id}"

        async with Client(mcp) as client:
            templates = await client.list_resource_templates()
            template = next(
                t for t in templates if t.uriTemplate == "test://template/{id}"
            )
            assert template.meta is not None
            assert set(template.meta["_fastmcp"]["tags"]) == {
                "template-example",
                "test-template-tag",
            }

    async def test_prompt_tags_in_meta_with_default_setting(self):
        """Test that prompt tags appear in meta under _fastmcp key with default setting."""
        mcp = FastMCP()

        @mcp.prompt(tags={"example", "test-tag"})
        def sample_prompt() -> str:
            return "Hello, world!"

        async with Client(mcp) as client:
            prompts = await client.list_prompts()
            prompt = next(p for p in prompts if p.name == "sample_prompt")
            assert prompt.meta is not None
            assert set(prompt.meta["_fastmcp"]["tags"]) == {"example", "test-tag"}

    async def test_tool_meta_with_include_fastmcp_meta_false(self):
        mcp = FastMCP(include_fastmcp_meta=False)

        @mcp.tool(tags={"tool-example", "test-tool-tag"})
        def sample_tool(x: int) -> int:
            """A sample tool."""
            return x * 2

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "sample_tool")
            # Meta should be None when include_fastmcp_meta is False
            assert tool.meta is None

    async def test_resource_meta_with_include_fastmcp_meta_false(self):
        mcp = FastMCP(include_fastmcp_meta=False)

        @mcp.resource(
            uri="test://resource", tags={"resource-example", "test-resource-tag"}
        )
        def sample_resource() -> str:
            """A sample resource."""
            return "resource content"

        async with Client(mcp) as client:
            resources = await client.list_resources()
            resource = next(r for r in resources if str(r.uri) == "test://resource")
            # Meta should be None when include_fastmcp_meta is False
            assert resource.meta is None

    async def test_resource_template_meta_with_include_fastmcp_meta_false(self):
        mcp = FastMCP(include_fastmcp_meta=False)

        @mcp.resource(
            "test://template/{id}", tags={"template-example", "test-template-tag"}
        )
        def sample_template(id: str) -> str:
            """A sample resource template."""
            return f"template content for {id}"

        async with Client(mcp) as client:
            templates = await client.list_resource_templates()
            template = next(
                t for t in templates if t.uriTemplate == "test://template/{id}"
            )
            # Meta should be None when include_fastmcp_meta is False
            assert template.meta is None

    async def test_prompt_meta_with_include_fastmcp_meta_false(self):
        mcp = FastMCP(include_fastmcp_meta=False)

        @mcp.prompt(tags={"example", "test-tag"})
        def sample_prompt() -> str:
            return "Hello, world!"

        async with Client(mcp) as client:
            prompts = await client.list_prompts()
            prompt = next(p for p in prompts if p.name == "sample_prompt")
            # Meta should be None when include_fastmcp_meta is False
            assert prompt.meta is None

    async def test_temporary_include_fastmcp_meta_setting(self):
        """Test that temporary_settings can toggle include_fastmcp_meta for new servers."""

        def make_server() -> FastMCP:
            mcp = FastMCP()

            @mcp.tool(tags={"test-tag"})
            def sample_tool(x: int) -> int:
                """A sample tool."""
                return x * 2

            return mcp

        # Default: meta should be present
        mcp = make_server()
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "sample_tool")
            assert tool.meta is not None
            assert set(tool.meta["_fastmcp"]["tags"]) == {"test-tag"}

        # With setting disabled: new server should not include meta
        with temporary_settings(include_fastmcp_meta=False):
            mcp = make_server()
            async with Client(mcp) as client:
                tools = await client.list_tools()
                tool = next(t for t in tools if t.name == "sample_tool")
                assert tool.meta is None

        # After context: new server should have meta again
        mcp = make_server()
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "sample_tool")
            assert tool.meta is not None
            assert set(tool.meta["_fastmcp"]["tags"]) == {"test-tag"}
