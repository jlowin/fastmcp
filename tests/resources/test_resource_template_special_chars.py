"""Tests for resource templates with special characters in parameter names."""

import urllib.parse

from mcp.types import TextResourceContents

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.resources.template import match_uri_template


class TestResourceTemplateSpecialChars:
    """Test resource templates with parameter names containing special characters."""

    def test_match_uri_template_special_chars(self):
        """Test that match_uri_template properly handles special characters."""
        template = "resource://{param-name}"
        uri = "resource://test-value"

        # This should match because param-name should be a valid parameter name
        # But it might not work if the parameter name parsing is broken
        match = match_uri_template(uri, template)

        assert match is not None, "Template should match the URI"
        assert match == {"param-name": "test-value"}, (
            "Parameter should be extracted correctly"
        )

    def test_match_uri_template_encoded_chars(self):
        """Test matching URIs with URL-encoded characters against a template."""
        template = "resource://{param}"

        # A URI with special characters that are URL-encoded
        uri = f"resource://{urllib.parse.quote('special value with spaces')}"

        # Call match_uri_template
        match = match_uri_template(uri, template)

        assert match is not None, "Template should match the URI"
        # We expect the value to be decoded by default
        assert match == {"param": "special value with spaces"}, (
            "URL-encoded parameter should be decoded by default"
        )

    def test_match_uri_template_with_symbol_in_param_name(self):
        """Test template with symbols in parameter names."""
        template = "resource://{param_with$symbol}"
        uri = "resource://test-value"

        # This should match if parameter parsing correctly handles symbol characters
        match = match_uri_template(uri, template)

        assert match is not None, "Template should match the URI"
        assert match == {"param_with$symbol": "test-value"}, (
            "Parameter should be extracted correctly"
        )

    async def test_resource_template_with_dash_in_param_name(self):
        """Test using a template with a dash in the parameter name."""
        mcp = FastMCP()

        @mcp.resource("test://{param-name}")
        def template_with_dash_param(param_name: str) -> str:
            return f"Value from parameter with dash: {param_name}"

        async with Client(mcp) as client:
            # Try to access the resource with a hyphenated parameter
            result = await client.read_resource("test://test-value")

            # This might fail if parameter name parsing is broken due to the dash
            assert isinstance(result[0], TextResourceContents)
            assert result[0].text == "Value from parameter with dash: test-value"

    async def test_resource_template_with_url_encoding(self):
        """Test resource template with URL-encoded characters in the URI."""
        mcp = FastMCP()

        @mcp.resource("test://{param}")
        def template_with_url_encoded_param(param: str) -> str:
            return f"Value: {param}"

        async with Client(mcp) as client:
            # Try accessing with a URL-encoded value
            encoded_value = urllib.parse.quote("value with spaces")
            result = await client.read_resource(f"test://{encoded_value}")

            # This will test if URI decoding happens correctly
            assert isinstance(result[0], TextResourceContents)
            assert (
                "value with spaces" in result[0].text or encoded_value in result[0].text
            )
