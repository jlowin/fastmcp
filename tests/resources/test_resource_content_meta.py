"""Test that _meta attributes are included in resource content responses."""

from pydantic import AnyUrl

from fastmcp import FastMCP
from fastmcp.client import Client


class TestResourceContentMetaRawResponse:
    """Test that _meta is present in raw MCP response."""

    async def test_raw_response_includes_meta(self):
        """Test that raw MCP response includes _meta in content."""
        mcp = FastMCP("TestServer")

        @mcp.resource(uri="test://raw", meta={"widgetDomain": "example.com"})
        def raw_resource() -> str:
            return "Raw content"

        async with Client(mcp) as client:
            # Get the raw MCP response
            result = await client.read_resource_mcp(AnyUrl("test://raw"))

            # Verify response structure
            assert result.contents is not None
            assert len(result.contents) == 1

            # Check the raw content object
            content = result.contents[0]
            assert hasattr(content, "meta")
            assert content.meta is not None
            assert "widgetDomain" in content.meta
            assert content.meta["widgetDomain"] == "example.com"

            # Verify serialization includes _meta
            content_dict = content.model_dump(by_alias=True)
            assert "_meta" in content_dict
            assert content_dict["_meta"]["widgetDomain"] == "example.com"

    async def test_raw_response_template_includes_meta(self):
        """Test that raw MCP response includes _meta for templates."""
        mcp = FastMCP("TestServer")

        @mcp.resource(
            uri="test://item/{item_id}", meta={"widgetDomain": "items.example.com"}
        )
        def item_resource(item_id: str) -> str:
            return f"Item: {item_id}"

        async with Client(mcp) as client:
            # Get the raw MCP response
            result = await client.read_resource_mcp(AnyUrl("test://item/456"))

            # Verify response structure
            assert result.contents is not None
            assert len(result.contents) == 1

            # Check the raw content object
            content = result.contents[0]
            assert hasattr(content, "meta")
            assert content.meta is not None
            assert "widgetDomain" in content.meta
            assert content.meta["widgetDomain"] == "items.example.com"

    async def test_raw_response_meta_serialization(self):
        """Test that _meta is properly serialized in the wire format."""
        mcp = FastMCP("TestServer")

        meta_data = {
            "widgetDomain": "example.com",
            "version": "2.0",
            "author": "test",
        }

        @mcp.resource(uri="test://serialize", meta=meta_data)
        def serialize_resource() -> str:
            return "Serialized content"

        async with Client(mcp) as client:
            # Get the raw MCP response
            result = await client.read_resource_mcp(AnyUrl("test://serialize"))

            # Verify the content
            content = result.contents[0]

            # Serialize to dict and verify all meta fields are present
            content_dict = content.model_dump(by_alias=True)
            assert "_meta" in content_dict

            # Verify all custom meta fields
            for key, value in meta_data.items():
                assert key in content_dict["_meta"]
                assert content_dict["_meta"][key] == value


class TestResourceContentMeta:
    """Test resource content _meta attribute."""

    async def test_resource_content_includes_meta(self):
        """Test that resource content includes _meta from resource.meta."""
        mcp = FastMCP("TestServer")

        @mcp.resource(uri="test://example", meta={"widgetDomain": "example.com"})
        def example_resource() -> str:
            return "Example content"

        async with Client(mcp) as client:
            # Read the resource
            result = await client.read_resource(AnyUrl("test://example"))

            # Verify we got content
            assert len(result) == 1
            content = result[0]

            # Verify the content has text
            assert content.text == "Example content"  # type: ignore[attr-defined]

            # Verify _meta is included in the content
            assert content.meta is not None
            assert "widgetDomain" in content.meta
            assert content.meta["widgetDomain"] == "example.com"

    async def test_resource_template_content_includes_meta(self):
        """Test that resource template content includes _meta from template.meta."""
        mcp = FastMCP("TestServer")

        @mcp.resource(
            uri="test://user/{user_id}", meta={"widgetDomain": "users.example.com"}
        )
        def user_resource(user_id: str) -> str:
            return f"User: {user_id}"

        async with Client(mcp) as client:
            # Read the resource via template
            result = await client.read_resource(AnyUrl("test://user/123"))

            # Verify we got content
            assert len(result) == 1
            content = result[0]

            # Verify the content has text
            assert content.text == "User: 123"  # type: ignore[attr-defined]

            # Verify _meta is included in the content
            assert content.meta is not None
            assert "widgetDomain" in content.meta
            assert content.meta["widgetDomain"] == "users.example.com"

    async def test_resource_content_without_meta(self):
        """Test that resources without meta still work."""
        mcp = FastMCP("TestServer")

        @mcp.resource(uri="test://no-meta")
        def no_meta_resource() -> str:
            return "Content without meta"

        async with Client(mcp) as client:
            # Read the resource
            result = await client.read_resource(AnyUrl("test://no-meta"))

            # Verify we got content
            assert len(result) == 1
            content = result[0]

            # Verify the content has text
            assert content.text == "Content without meta"  # type: ignore[attr-defined]

            # Meta might be None or might have fastmcp meta depending on settings
            # Just verify this doesn't crash

    async def test_resource_content_meta_with_multiple_fields(self):
        """Test resource content with multiple meta fields."""
        mcp = FastMCP("TestServer")

        meta_data = {
            "widgetDomain": "example.com",
            "version": "1.0",
            "category": "documentation",
        }

        @mcp.resource(uri="test://multi-meta", meta=meta_data)
        def multi_meta_resource() -> str:
            return "Content with multiple meta fields"

        async with Client(mcp) as client:
            # Read the resource
            result = await client.read_resource(AnyUrl("test://multi-meta"))

            # Verify we got content
            assert len(result) == 1
            content = result[0]

            # Verify the content has text
            assert content.text == "Content with multiple meta fields"  # type: ignore[attr-defined]

            # Verify all meta fields are included
            assert content.meta is not None
            assert "widgetDomain" in content.meta
            assert content.meta["widgetDomain"] == "example.com"
            assert "version" in content.meta
            assert content.meta["version"] == "1.0"
            assert "category" in content.meta
            assert content.meta["category"] == "documentation"
