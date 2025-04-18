"""Tests for the MCPMixin class."""

import pytest

from contrib.mcp_mixin.mcp_mixin import (
    _DEFAULT_SEPARATOR_PROMPT,
    _DEFAULT_SEPARATOR_RESOURCE,
    _DEFAULT_SEPARATOR_TOOL,
    MCPMixin,
    mcp_prompt,
    mcp_resource,
    mcp_tool,
)
from fastmcp import FastMCP


class TestMCPMixin:
    """Test suite for MCPMixin functionality."""

    def test_initialization(self):
        """Test that a class inheriting MCPMixin can be initialized."""

        class MyMixin(MCPMixin):
            pass

        instance = MyMixin()
        assert instance is not None

    # --- Tool Registration Tests ---
    @pytest.mark.parametrize(
        "prefix, separator, expected_key, unexpected_key",
        [
            (
                None,
                _DEFAULT_SEPARATOR_TOOL,
                "sample_tool",
                f"None{_DEFAULT_SEPARATOR_TOOL}sample_tool",
            ),
            (
                "pref",
                _DEFAULT_SEPARATOR_TOOL,
                f"pref{_DEFAULT_SEPARATOR_TOOL}sample_tool",
                "sample_tool",
            ),
            (
                "pref",
                "-",
                "pref-sample_tool",
                f"pref{_DEFAULT_SEPARATOR_TOOL}sample_tool",
            ),
        ],
        ids=["No prefix", "Default separator", "Custom separator"],
    )
    def test_tool_registration(self, prefix, separator, expected_key, unexpected_key):
        """Test tool registration with prefix and separator variations."""
        mcp = FastMCP()

        class MyToolMixin(MCPMixin):
            @mcp_tool()
            def sample_tool(self):
                pass

        instance = MyToolMixin()
        instance.register_tools(mcp, prefix=prefix, separator=separator)

        registered_tools = mcp.get_tools()
        assert expected_key in registered_tools
        assert unexpected_key not in registered_tools

    @pytest.mark.parametrize(
        "prefix, separator, expected_uri_key, expected_name, unexpected_uri_key",
        [
            (
                None,
                _DEFAULT_SEPARATOR_RESOURCE,
                "test://resource",
                "sample_resource",
                f"None{_DEFAULT_SEPARATOR_RESOURCE}test://resource",
            ),
            (
                "pref",
                _DEFAULT_SEPARATOR_RESOURCE,
                f"pref{_DEFAULT_SEPARATOR_RESOURCE}test://resource",
                f"pref{_DEFAULT_SEPARATOR_RESOURCE}sample_resource",
                "test://resource",
            ),
            (
                "pref",
                "fff",
                "prefffftest://resource",
                "preffffsample_resource",
                f"pref{_DEFAULT_SEPARATOR_RESOURCE}test://resource",
            ),
        ],
        ids=["No prefix", "Default separator", "Custom separator"],
    )
    def test_resource_registration(
        self, prefix, separator, expected_uri_key, expected_name, unexpected_uri_key
    ):
        """Test resource registration with prefix and separator variations."""
        mcp = FastMCP()

        class MyResourceMixin(MCPMixin):
            @mcp_resource(uri="test://resource")
            def sample_resource(self):
                pass

        instance = MyResourceMixin()
        instance.register_resources(mcp, prefix=prefix, separator=separator)

        registered_resources = mcp.get_resources()
        assert expected_uri_key in registered_resources
        assert registered_resources[expected_uri_key].name == expected_name
        assert unexpected_uri_key not in registered_resources

    @pytest.mark.parametrize(
        "prefix, separator, expected_name, unexpected_name",
        [
            (
                None,
                _DEFAULT_SEPARATOR_PROMPT,
                "sample_prompt",
                f"None{_DEFAULT_SEPARATOR_PROMPT}sample_prompt",
            ),
            (
                "pref",
                _DEFAULT_SEPARATOR_PROMPT,
                f"pref{_DEFAULT_SEPARATOR_PROMPT}sample_prompt",
                "sample_prompt",
            ),
            (
                "pref",
                ":",
                "pref:sample_prompt",
                f"pref{_DEFAULT_SEPARATOR_PROMPT}sample_prompt",
            ),
        ],
        ids=["No prefix", "Default separator", "Custom separator"],
    )
    def test_prompt_registration(
        self, prefix, separator, expected_name, unexpected_name
    ):
        """Test prompt registration with prefix and separator variations."""
        mcp = FastMCP()

        class MyPromptMixin(MCPMixin):
            @mcp_prompt()
            def sample_prompt(self):
                pass

        instance = MyPromptMixin()
        instance.register_prompts(mcp, prefix=prefix, separator=separator)

        registered_prompt_names = {p.name for p in mcp.list_prompts()}
        assert expected_name in registered_prompt_names
        assert unexpected_name not in registered_prompt_names

    def test_register_all_no_prefix(self):
        """Test register_all method registers all types without a prefix."""
        mcp = FastMCP()

        class MyFullMixin(MCPMixin):
            @mcp_tool()
            def tool_all(self):
                pass

            @mcp_resource(uri="res://all")
            def resource_all(self):
                pass

            @mcp_prompt()
            def prompt_all(self):
                pass

        instance = MyFullMixin()
        instance.register_all(mcp)

        assert "tool_all" in mcp.get_tools()
        assert "res://all" in mcp.get_resources()
        assert "prompt_all" in {p.name for p in mcp.list_prompts()}

    def test_register_all_with_prefix_default_separators(self):
        """Test register_all method registers all types with a prefix and default separators."""
        mcp = FastMCP()

        class MyFullMixinPrefixed(MCPMixin):
            @mcp_tool()
            def tool_all_p(self):
                pass

            @mcp_resource(uri="res://all_p")
            def resource_all_p(self):
                pass

            @mcp_prompt()
            def prompt_all_p(self):
                pass

        instance = MyFullMixinPrefixed()
        instance.register_all(mcp, prefix="all")

        assert f"all{_DEFAULT_SEPARATOR_TOOL}tool_all_p" in mcp.get_tools()
        assert f"all{_DEFAULT_SEPARATOR_RESOURCE}res://all_p" in mcp.get_resources()
        assert f"all{_DEFAULT_SEPARATOR_PROMPT}prompt_all_p" in {
            p.name for p in mcp.list_prompts()
        }

    def test_register_all_with_prefix_custom_separators(self):
        """Test register_all method registers all types with a prefix and custom separators."""
        mcp = FastMCP()

        class MyFullMixinCustomSep(MCPMixin):
            @mcp_tool()
            def tool_cust(self):
                pass

            @mcp_resource(uri="res://cust")
            def resource_cust(self):
                pass

            @mcp_prompt()
            def prompt_cust(self):
                pass

        instance = MyFullMixinCustomSep()
        instance.register_all(
            mcp,
            prefix="cust",
            tool_separator="-",
            resource_separator="::",
            prompt_separator=".",
        )

        assert "cust-tool_cust" in mcp.get_tools()
        assert "cust::res://cust" in mcp.get_resources()
        assert "cust.prompt_cust" in {p.name for p in mcp.list_prompts()}

        # Check default separators weren't used
        assert f"cust{_DEFAULT_SEPARATOR_TOOL}tool_cust" not in mcp.get_tools()
        assert f"cust{_DEFAULT_SEPARATOR_RESOURCE}res://cust" not in mcp.get_resources()
        assert f"cust{_DEFAULT_SEPARATOR_PROMPT}prompt_cust" not in {
            p.name for p in mcp.list_prompts()
        }
