"""Tests for external resources and validation middleware."""

import json

import pytest
from mcp.types import TextContent, TextResourceContents
from pydantic import AnyUrl

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.external_resources import (
    ExternalResource,
    ExternalResourceTemplate,
    ValidationMiddleware,
    register_external_resources,
)
from fastmcp.exceptions import ToolError

# Tests for ExternalResource and ExternalResourceTemplate classes


async def test_external_resource_basic():
    """Test basic ExternalResource functionality."""
    resource = ExternalResource(
        uri=AnyUrl("s3://bucket/file.csv"),
        name="Test File",
        description="A test CSV file",
        mime_type="text/csv",
        meta={"size": "100MB", "created": "2024-01-01"},
    )

    # Check attributes
    assert str(resource.uri) == "s3://bucket/file.csv"
    assert resource.name == "Test File"
    assert resource.description == "A test CSV file"
    assert resource.mime_type == "text/csv"
    assert resource.meta == {"size": "100MB", "created": "2024-01-01"}

    # Test read method
    content = await resource.read()
    data = json.loads(content)
    assert data["uri"] == "s3://bucket/file.csv"
    assert data["name"] == "Test File"
    assert data["description"] == "A test CSV file"
    assert data["mime_type"] == "text/csv"
    assert data["meta"] == {"size": "100MB", "created": "2024-01-01"}


async def test_external_resource_minimal():
    """Test ExternalResource with minimal fields."""
    resource = ExternalResource(
        uri=AnyUrl("https://api.example.com/data"),
        name="API Data",
    )

    # Default values
    assert resource.description is None
    assert resource.mime_type == "text/plain"  # Default from parent
    assert resource.meta is None

    # Test read
    content = await resource.read()
    data = json.loads(content)
    assert data["uri"] == "https://api.example.com/data"
    assert data["name"] == "API Data"
    assert data["description"] is None
    assert data["mime_type"] == "text/plain"
    assert data["meta"] is None


async def test_external_resource_template_basic():
    """Test basic ExternalResourceTemplate functionality."""
    template = ExternalResourceTemplate(
        uri_template="s3://bucket/data/{year}/{month}",
        name="Monthly Data",
        parameters=["year", "month"],
        description="Monthly data files",
        mime_type="application/json",
        meta={"format": "parquet"},
    )

    # Check attributes
    assert template.uri_template == "s3://bucket/data/{year}/{month}"
    assert template.name == "Monthly Data"
    assert template.description == "Monthly data files"
    assert template.mime_type == "application/json"
    assert template.meta == {"format": "parquet"}

    # Check generated parameters schema
    assert template.parameters["type"] == "object"
    assert "year" in template.parameters["properties"]
    assert "month" in template.parameters["properties"]
    assert template.parameters["required"] == ["year", "month"]

    # Test read method with arguments
    content = await template.read({"year": "2024", "month": "01"})
    data = json.loads(content)
    assert data["uri_template"] == "s3://bucket/data/{year}/{month}"
    assert data["name"] == "Monthly Data"
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

    # Test read
    content = await template.read({"endpoint": "users", "limit": "10"})
    data = json.loads(content)
    assert data["resolved_args"] == {"endpoint": "users", "limit": "10"}


async def test_register_external_resources():
    """Test registering external resources with a FastMCP app."""
    app = FastMCP("Test External Resources")

    resources = [
        ExternalResource(
            uri=AnyUrl("s3://bucket/file1.csv"),
            name="File 1",
        ),
        ExternalResource(
            uri=AnyUrl("s3://bucket/file2.csv"),
            name="File 2",
        ),
        ExternalResourceTemplate(
            uri_template="https://api.example.com/{endpoint}",
            name="API Template",
            parameters=["endpoint"],
        ),
    ]

    register_external_resources(app, resources)

    # Check resources were registered
    async with Client(app) as client:
        # List resources
        resources_list = await client.list_resources()
        assert len(resources_list) == 2
        uris = [str(r.uri) for r in resources_list]
        assert "s3://bucket/file1.csv" in uris
        assert "s3://bucket/file2.csv" in uris

        # List templates
        templates_list = await client.list_resource_templates()
        assert len(templates_list) == 1
        assert templates_list[0].uriTemplate == "https://api.example.com/{endpoint}"


async def test_external_resource_read_through_client():
    """Test reading external resources through the MCP client."""
    app = FastMCP("Test Read External Resources")

    resource = ExternalResource(
        uri=AnyUrl("s3://bucket/important.csv"),
        name="Important Data",
        description="Critical business data",
        mime_type="text/csv",
        meta={"confidential": True, "size": "500MB"},
    )

    app.add_resource(resource)

    async with Client(app) as client:
        # Read the resource
        contents = await client.read_resource("s3://bucket/important.csv")
        assert len(contents) == 1

        # Parse the returned content
        assert isinstance(contents[0], TextResourceContents)
        data = json.loads(contents[0].text)
        assert data["uri"] == "s3://bucket/important.csv"
        assert data["name"] == "Important Data"
        assert data["description"] == "Critical business data"
        assert data["mime_type"] == "text/csv"
        assert data["meta"]["confidential"] is True
        assert data["meta"]["size"] == "500MB"


async def test_external_resource_template_read_through_client():
    """Test reading template resources through the MCP client."""
    app = FastMCP("Test Read Template Resources")

    template = ExternalResourceTemplate(
        uri_template="https://api.weather.com/v1/cities/{city}/forecast",
        name="Weather API",
        parameters=["city"],
        description="Get weather forecast for any city",
        mime_type="application/json",
        meta={"api_version": "v1"},
    )

    app.add_template(template)

    async with Client(app) as client:
        # Read a specific instance
        contents = await client.read_resource(
            "https://api.weather.com/v1/cities/london/forecast"
        )
        assert len(contents) == 1

        # Parse the returned content
        assert isinstance(contents[0], TextResourceContents)
        data = json.loads(contents[0].text)
        assert (
            data["uri_template"] == "https://api.weather.com/v1/cities/{city}/forecast"
        )
        assert data["name"] == "Weather API"
        assert data["resolved_args"]["city"] == "london"
        assert data["meta"]["api_version"] == "v1"


async def test_external_resource_different_uri_schemes():
    """Test ExternalResource with various URI schemes."""
    schemes = [
        ("s3://bucket/file.csv", "S3 File"),
        ("gs://bucket/data.json", "Google Cloud Storage"),
        ("https://api.example.com/data", "HTTPS API"),
        ("http://localhost:8080/test", "HTTP Local"),
        ("ftp://server.com/file.txt", "FTP File"),
        ("file:///home/user/data.csv", "Local File"),
        ("mongodb://localhost:27017/db", "MongoDB"),
        ("redis://localhost:6379/0", "Redis"),
    ]

    for uri_str, name in schemes:
        resource = ExternalResource(
            uri=AnyUrl(uri_str),
            name=name,
        )
        assert str(resource.uri) == uri_str
        assert resource.name == name

        # Should be readable
        content = await resource.read()
        data = json.loads(content)
        assert data["uri"] == uri_str


async def test_external_resource_inheritance():
    """Test that ExternalResource properly inherits from Resource."""
    resource = ExternalResource(
        uri=AnyUrl("s3://bucket/file.csv"),
        name="Test Resource",
    )

    # Should have all Resource base class features
    assert hasattr(resource, "uri")
    assert hasattr(resource, "name")
    assert hasattr(resource, "description")
    assert hasattr(resource, "mime_type")
    assert hasattr(resource, "meta")
    assert hasattr(resource, "enabled")
    assert hasattr(resource, "tags")

    # Should be enabled by default
    assert resource.enabled is True

    # Can use tags
    resource.tags.add("external")
    resource.tags.add("s3")
    assert "external" in resource.tags
    assert "s3" in resource.tags


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

    # Tool with AnyUrl parameter - will be validated
    @app.tool()
    async def fetch_data(url: AnyUrl) -> str:
        """Fetch data from a URL."""
        return f"Fetching from: {url}"

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
            await client.call_tool("fetch_data", {"url": "https://external.com"})

        assert "Unknown resource URI 'https://external.com'" in str(exc_info.value)


async def test_closed_world_tool_validation(app_with_middleware):
    """Test that tools with openWorldHint=False are validated."""
    async with Client(app_with_middleware) as client:
        # Valid resource should work
        result = await client.call_tool(
            "secure_process", {"uri": "resource://test-data"}
        )
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "Secure processing: resource://test-data" in content.text

        # Invalid resource should fail
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("secure_process", {"uri": "https://unknown.com"})

        assert "Unknown resource URI" in str(exc_info.value)


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


async def test_non_uri_parameters_not_validated(app_with_middleware):
    """Test that non-URI parameters are not validated."""
    app = app_with_middleware

    @app.tool()
    async def process_data(data: str, count: int) -> str:
        """Process data with non-URI parameters."""
        return f"Processing {data} {count} times"

    async with Client(app) as client:
        # Non-URI parameters should not be validated
        result = await client.call_tool("process_data", {"data": "test", "count": 5})
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "Processing test 5 times" in content.text


async def test_missing_tool_handled_gracefully(app_with_middleware):
    """Test that missing tools are handled by the normal error path."""
    async with Client(app_with_middleware) as client:
        # Missing tool should raise normal error, not validation error
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("missing_tool", {"uri": "resource://test"})

        # Should not be a validation error
        assert "Unknown resource URI" not in str(exc_info.value)


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


async def test_empty_arguments_handled(app_with_middleware):
    """Test that tools with no arguments are handled correctly."""
    app = app_with_middleware

    @app.tool()
    async def no_args_tool() -> str:
        """Tool with no arguments."""
        return "No arguments"

    async with Client(app) as client:
        result = await client.call_tool("no_args_tool", {})
        assert len(result.content) > 0
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "No arguments" in content.text
