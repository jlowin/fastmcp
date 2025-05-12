"""Tests for fixed resource templates with special characters in parameter names."""

from fastmcp.resources.template import match_uri_template

# Create a custom target in the Makefile to test our fix
# make test-resource-template-fix


class TestResourceTemplateSpecialCharsFixed:
    """Test resource templates with parameter names containing special characters."""

    def test_fixed_match_uri_template_special_chars(self):
        """Test that the fixed implementation properly handles special characters in parameter names."""
        # This is what the fixed implementation should be able to handle
        template = "resource://{param-name}"
        uri = "resource://test-value"

        # Test the match_uri_template function
        match = match_uri_template(uri, template)

        # This should now work with the fixed implementation
        assert match is not None, "Fixed implementation should match the URI"
        assert match == {"param-name": "test-value"}, (
            "Parameter should be extracted correctly"
        )

    def test_create_fix_for_resource_template(self):
        """Test that the resource template parameter mapping works."""
        template = "resource://{param-with-special-chars}"
        uri = "resource://test-value"

        # Test our match_uri_template function from the fixed implementation
        result = match_uri_template(uri, template)

        assert result is not None, "The fixed implementation should match the URI"
        assert result == {"param-with-special-chars": "test-value"}, (
            "Parameters should be extracted correctly"
        )
