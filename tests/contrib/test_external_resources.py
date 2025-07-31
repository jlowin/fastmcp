"""Tests for external resources and validation middleware."""

import json

import pytest
from mcp.types import TextContent
from pydantic import AnyUrl

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.external_resources import (
    ExternalResource,
    ExternalResourceTemplate,
    ValidationMiddleware,
)
from fastmcp.exceptions import ToolError


# Tests for ExternalResource and ExternalResourceTemplate specific features


async def test_external_resource_returns_metadata():
    """Test that ExternalResource returns metadata as JSON."""
    resource = ExternalResource(
        uri=AnyUrl("s3://bucket/file.csv"),
        name="Test File",
        description="A test CSV file",
        mime_type="text/csv",
        meta={"size": "100MB", "created": "2024-01-01"},
    )

    # Test read method returns metadata
    content = await resource.read()
    data = json.loads(content)
    assert data["uri"] == "s3://bucket/file.csv"
    assert data["name"] == "Test File"
    assert data["description"] == "A test CSV file"
    assert data["mime_type"] == "text/csv"
    assert data["meta"] == {"size": "100MB", "created": "2024-01-01"}


async def test_external_resource_template_parameter_generation():
    """Test ExternalResourceTemplate generates correct parameter schema."""
    template = ExternalResourceTemplate(
        uri_template="s3://bucket/data/{year}/{month}",
        name="Monthly Data",
        parameters=["year", "month"],
        description="Monthly data files",
        mime_type="application/json",
        meta={"format": "parquet"},
    )

    # Check generated parameters schema
    assert template.parameters["type"] == "object"
    assert "year" in template.parameters["properties"]
    assert "month" in template.parameters["properties"]
    assert template.parameters["required"] == ["year", "month"]

    # Test read method includes resolved args
    content = await template.read({"year": "2024", "month": "01"})
    data = json.loads(content)
    assert data["resolved_args"] == {"year": "2024", "month": "01"}


async def test_external_resource_template_optional_params():
    """Test ExternalResourceTemplate with optional parameters."""
    template = ExternalResourceTemplate(
        uri_template="https://api.example.com/v1/{endpoint}?limit={limit}",
        name="API Endpoint",
        parameters=["endpoint", "limit"],
        required=["endpoint"],  # Only endpoint is required
    )

    # Check that only endpoint is required
    assert template.parameters["required"] == ["endpoint"]
    assert "limit" in template.parameters["properties"]


# Tests for ValidationMiddleware


@pytest.fixture
def app_with_middleware():
    """Create a FastMCP app with external resource validation."""
    app = FastMCP("Test External Resources")

    # Add validation middleware
    app.add_middleware(ValidationMiddleware(app))

    # Add some resources
    @app.resource("resource://test-data")
    async def test_data():
        return "Test data content"

    @app.resource("resource://config/{name}")
    async def config_resource(name: str):
        return f"Config for {name}"

    # Tool without annotation - will be validated (secure by default)
    @app.tool()
    async def process_resource(resource_uri: AnyUrl) -> str:
        """Process a resource by URI."""
        return f"Processing: {resource_uri}"

    # Tool with openWorldHint=False - will be validated
    @app.tool(annotations={"openWorldHint": False})
    async def secure_process(uri: AnyUrl) -> str:
        """Securely process a resource."""
        return f"Secure processing: {uri}"

    # Tool with openWorldHint=True - will NOT be validated
    @app.tool(annotations={"openWorldHint": True})
    async def process_external(external_uri: AnyUrl) -> str:
        """Process an external resource."""
        return f"Processing external: {external_uri}"

    return app


async def test_default_validation_for_tool_without_annotation(app_with_middleware):
    """Test that tools without annotation are validated by default."""
    async with Client(app_with_middleware) as client:
        # Valid resource should work
        result = await client.call_tool(
            "process_resource", {"resource_uri": "resource://test-data"}
        )
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "Processing: resource://test-data" in content.text

        # Invalid resource should fail
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "process_resource", {"resource_uri": "resource://invalid"}
            )

        assert "Unknown resource URI 'resource://invalid'" in str(exc_info.value)
        assert "To allow any URI, set openWorldHint=True" in str(exc_info.value)


async def test_validation_with_resource_template(app_with_middleware):
    """Test validation with a resource template."""
    async with Client(app_with_middleware) as client:
        # URI matching template should work
        result = await client.call_tool(
            "process_resource", {"resource_uri": "resource://config/production"}
        )
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "Processing: resource://config/production" in content.text


async def test_validation_with_anyurl_type(app_with_middleware):
    """Test validation detects AnyUrl type parameters."""
    async with Client(app_with_middleware) as client:
        # Should validate AnyUrl parameters
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "process_resource", {"resource_uri": "https://external.com"}
            )

        assert "Unknown resource URI 'https://external.com'" in str(exc_info.value)


async def test_open_world_tool_no_validation(app_with_middleware):
    """Test that tools with openWorldHint=True are NOT validated."""
    async with Client(app_with_middleware) as client:
        # Open world tool should accept any URI
        result = await client.call_tool(
            "process_external", {"external_uri": "https://any.external.com"}
        )
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "Processing external: https://any.external.com" in content.text


async def test_mixed_parameters_validation(app_with_middleware):
    """Test validation with mixed parameter types."""
    app = app_with_middleware

    @app.tool()
    async def analyze(name: str, source: AnyUrl, verbose: bool = False) -> str:
        """Analyze a resource with mixed parameters."""
        return f"Analyzing {name} from {source} (verbose={verbose})"

    async with Client(app) as client:
        # Valid resource
        result = await client.call_tool(
            "analyze",
            {"name": "test", "source": "resource://test-data", "verbose": True},
        )
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "Analyzing test from resource://test-data" in content.text

        # Invalid resource
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "analyze",
                {"name": "test", "source": "https://invalid.com", "verbose": False},
            )

        assert "Unknown resource URI 'https://invalid.com'" in str(exc_info.value)