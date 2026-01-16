"""Tests for component versioning functionality."""
# ruff: noqa: F811  # Intentional function redefinition for version testing

from __future__ import annotations

from mcp.types import TextContent

from fastmcp import FastMCP
from fastmcp.utilities.versions import (
    VersionKey,
    compare_versions,
    is_version_greater,
)


class TestVersionKey:
    """Tests for VersionKey comparison class."""

    def test_none_sorts_lowest(self):
        """None (unversioned) should sort lower than any version."""
        assert VersionKey(None) < VersionKey("1.0")
        assert VersionKey(None) < VersionKey("0.1")
        assert VersionKey(None) < VersionKey("anything")

    def test_none_equals_none(self):
        """Two None versions should be equal."""
        assert VersionKey(None) == VersionKey(None)
        assert not (VersionKey(None) < VersionKey(None))
        assert not (VersionKey(None) > VersionKey(None))

    def test_pep440_versions_compared_semantically(self):
        """Valid PEP 440 versions should compare semantically."""
        assert VersionKey("1.0") < VersionKey("2.0")
        assert VersionKey("1.0") < VersionKey("1.1")
        assert VersionKey("1.9") < VersionKey("1.10")  # Semantic, not string
        assert VersionKey("2") < VersionKey("10")  # Semantic, not string

    def test_v_prefix_stripped(self):
        """Versions with 'v' prefix should be handled correctly."""
        assert VersionKey("v1.0") == VersionKey("1.0")
        assert VersionKey("v2.0") > VersionKey("v1.0")

    def test_string_fallback_for_invalid_versions(self):
        """Invalid PEP 440 versions should fall back to string comparison."""
        # Dates are not valid PEP 440
        assert VersionKey("2024-01-01") < VersionKey("2025-01-01")
        # String comparison (lexicographic)
        assert VersionKey("alpha") < VersionKey("beta")

    def test_pep440_sorts_before_strings(self):
        """PEP 440 versions sort before invalid string versions."""
        # "1.0" is valid PEP 440, "not-semver" is not
        assert VersionKey("1.0") < VersionKey("not-semver")
        assert VersionKey("999.0") < VersionKey("aaa")  # PEP 440 < string

    def test_repr(self):
        """Test string representation."""
        assert repr(VersionKey("1.0")) == "VersionKey('1.0')"
        assert repr(VersionKey(None)) == "VersionKey(None)"


class TestVersionFunctions:
    """Tests for version comparison functions."""

    def test_compare_versions(self):
        """Test compare_versions function."""
        assert compare_versions("1.0", "2.0") == -1
        assert compare_versions("2.0", "1.0") == 1
        assert compare_versions("1.0", "1.0") == 0
        assert compare_versions(None, "1.0") == -1
        assert compare_versions("1.0", None) == 1
        assert compare_versions(None, None) == 0

    def test_is_version_greater(self):
        """Test is_version_greater function."""
        assert is_version_greater("2.0", "1.0")
        assert not is_version_greater("1.0", "2.0")
        assert not is_version_greater("1.0", "1.0")
        assert is_version_greater("1.0", None)
        assert not is_version_greater(None, "1.0")


class TestComponentVersioning:
    """Tests for versioning in FastMCP components."""

    async def test_tool_with_version(self):
        """Tool version should be reflected in key."""
        mcp = FastMCP()

        @mcp.tool(version="2.0")
        def my_tool(x: int) -> int:
            return x * 2

        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "my_tool"
        assert tools[0].version == "2.0"
        assert tools[0].key == "tool:my_tool@2.0"

    async def test_tool_without_version(self):
        """Tool without version should have @ sentinel in key but empty version."""
        mcp = FastMCP()

        @mcp.tool
        def my_tool(x: int) -> int:
            return x * 2

        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version is None
        # Keys always have @ sentinel for unambiguous parsing
        assert tools[0].key == "tool:my_tool@"

    async def test_tool_version_as_int(self):
        """Tool version as int should be coerced to string."""
        mcp = FastMCP()

        @mcp.tool(version=2)
        def my_tool(x: int) -> int:
            return x * 2

        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "2"
        assert tools[0].key == "tool:my_tool@2"

    async def test_multiple_tool_versions_deduplicated(self):
        """Multiple versions of same tool should deduplicate to highest."""
        mcp = FastMCP()

        @mcp.tool(version="1.0")
        def add(x: int, y: int) -> int:
            return x + y

        @mcp.tool(version="2.0")
        def add(x: int, y: int, z: int = 0) -> int:
            return x + y + z

        tools = await mcp.get_tools()
        # Should only show the highest version
        assert len(tools) == 1
        assert tools[0].name == "add"
        assert tools[0].version == "2.0"

    async def test_call_tool_invokes_highest_version(self):
        """Calling a tool by name should invoke the highest version."""
        mcp = FastMCP()

        @mcp.tool(version="1.0")
        def add(x: int, y: int) -> int:
            return x + y

        @mcp.tool(version="2.0")
        def add(x: int, y: int) -> int:
            return (x + y) * 10  # Different behavior to distinguish

        result = await mcp.call_tool("add", {"x": 1, "y": 2})
        # Should invoke v2.0 which multiplies by 10
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "30"

    async def test_unversioned_tool_loses_to_versioned(self):
        """Unversioned tool should be superseded by versioned tool."""
        mcp = FastMCP()

        @mcp.tool
        def my_tool() -> str:
            return "unversioned"

        @mcp.tool(version="1.0")
        def my_tool() -> str:
            return "v1.0"

        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "1.0"

        result = await mcp.call_tool("my_tool", {})
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "v1.0"

    async def test_resource_with_version(self):
        """Resource version should work like tool version."""
        mcp = FastMCP()

        @mcp.resource("file://config", version="1.0")
        def config_v1() -> str:
            return "config v1"

        @mcp.resource("file://config", version="2.0")
        def config_v2() -> str:
            return "config v2"

        resources = await mcp.get_resources()
        assert len(resources) == 1
        assert resources[0].version == "2.0"

    async def test_prompt_with_version(self):
        """Prompt version should work like tool version."""
        mcp = FastMCP()

        @mcp.prompt(version="1.0")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @mcp.prompt(version="2.0")
        def greet(name: str) -> str:
            return f"Greetings, {name}!"

        prompts = await mcp.get_prompts()
        assert len(prompts) == 1
        assert prompts[0].version == "2.0"


class TestVersionSorting:
    """Tests for version sorting behavior."""

    async def test_semantic_version_sorting(self):
        """Versions should sort semantically, not lexicographically."""
        mcp = FastMCP()

        # Add versions out of order
        @mcp.tool(version="1")
        def count() -> int:
            return 1

        @mcp.tool(version="10")
        def count() -> int:
            return 10

        @mcp.tool(version="2")
        def count() -> int:
            return 2

        tools = await mcp.get_tools()
        # Should keep v10 as highest (semantic: 10 > 2 > 1)
        assert len(tools) == 1
        assert tools[0].version == "10"

        result = await mcp.call_tool("count", {})
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "10"

    async def test_semver_sorting(self):
        """Full semver versions should sort correctly."""
        mcp = FastMCP()

        @mcp.tool(version="1.2.3")
        def info() -> str:
            return "1.2.3"

        @mcp.tool(version="1.2.10")
        def info() -> str:
            return "1.2.10"

        @mcp.tool(version="1.10.1")
        def info() -> str:
            return "1.10.1"

        tools = await mcp.get_tools()
        assert len(tools) == 1
        # 1.10.1 > 1.2.10 > 1.2.3 (semantic)
        assert tools[0].version == "1.10.1"

    async def test_v_prefix_normalized(self):
        """Versions with 'v' prefix should compare correctly."""
        mcp = FastMCP()

        @mcp.tool(version="v1.0")
        def calc() -> int:
            return 1

        @mcp.tool(version="v2.0")
        def calc() -> int:
            return 2

        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "v2.0"


class TestMountedServerVersioning:
    """Tests for versioning in mounted servers (FastMCPProvider)."""

    async def test_mounted_tool_preserves_version(self):
        """Mounted tools should preserve their version info."""
        child = FastMCP("Child")

        @child.tool(version="2.0")
        def add(x: int, y: int) -> int:
            return x + y

        parent = FastMCP("Parent")
        parent.mount(child, "child")

        tools = await parent.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "child_add"
        assert tools[0].version == "2.0"

    async def test_mounted_resource_preserves_version(self):
        """Mounted resources should preserve their version info."""
        child = FastMCP("Child")

        @child.resource("file://config", version="1.5")
        def config() -> str:
            return "config data"

        parent = FastMCP("Parent")
        parent.mount(child, "child")

        resources = await parent.get_resources()
        assert len(resources) == 1
        assert resources[0].version == "1.5"

    async def test_mounted_prompt_preserves_version(self):
        """Mounted prompts should preserve their version info."""
        child = FastMCP("Child")

        @child.prompt(version="3.0")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        parent = FastMCP("Parent")
        parent.mount(child, "child")

        prompts = await parent.get_prompts()
        assert len(prompts) == 1
        assert prompts[0].name == "child_greet"
        assert prompts[0].version == "3.0"

    async def test_mounted_get_tool_with_version(self):
        """Should be able to get specific version from mounted server."""
        child = FastMCP("Child")

        @child.tool(version="1.0")
        def calc() -> int:
            return 1

        @child.tool(version="2.0")
        def calc() -> int:
            return 2

        parent = FastMCP("Parent")
        parent.mount(child, "child")

        # Get highest version (default)
        tool = await parent.get_tool("child_calc")
        assert tool is not None
        assert tool.version == "2.0"

        # Get specific version
        tool_v1 = await parent.get_tool("child_calc", version="1.0")
        assert tool_v1 is not None
        assert tool_v1.version == "1.0"

    async def test_mounted_multiple_versions_deduplicates(self):
        """Mounted server with multiple versions should show only highest."""
        child = FastMCP("Child")

        @child.tool(version="1.0")
        def my_tool() -> str:
            return "v1"

        @child.tool(version="3.0")
        def my_tool() -> str:
            return "v3"

        @child.tool(version="2.0")
        def my_tool() -> str:
            return "v2"

        parent = FastMCP("Parent")
        parent.mount(child, "child")

        tools = await parent.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "3.0"

    async def test_mounted_call_tool_uses_highest_version(self):
        """Calling mounted tool should use highest version."""
        child = FastMCP("Child")

        @child.tool(version="1.0")
        def double(x: int) -> int:
            return x * 2

        @child.tool(version="2.0")
        def double(x: int) -> int:
            return x * 2 + 100  # Different behavior

        parent = FastMCP("Parent")
        parent.mount(child, "child")

        result = await parent.call_tool("child_double", {"x": 5})
        # Should use v2.0 which adds 100
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "110"


class TestVersionFilter:
    """Tests for VersionFilter transform."""

    async def test_version_lt_filters_high_versions(self):
        """VersionFilter(version_lt='3.0') hides v3+, shows v1 and v2."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.tool(version="1.0")
        def calc() -> int:
            return 1

        @mcp.tool(version="2.0")
        def calc() -> int:
            return 2

        @mcp.tool(version="3.0")
        def calc() -> int:
            return 3

        # Without filter, should show v3 (highest)
        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "3.0"

        # With filter, should show v2 (highest below 3.0)
        mcp.add_transform(VersionFilter(version_lt="3.0"))
        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "2.0"

    async def test_version_gte_filters_low_versions(self):
        """VersionFilter(version_gte='2.0') hides v1, shows v2 and v3."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.tool(version="1.0")
        def add(x: int) -> int:
            return x + 1

        @mcp.tool(version="2.0")
        def add(x: int) -> int:
            return x + 2

        @mcp.tool(version="3.0")
        def add(x: int) -> int:
            return x + 3

        mcp.add_transform(VersionFilter(version_gte="2.0"))

        # Should show v3 (highest >= 2.0)
        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "3.0"

        # All versions >= 2.0 should be available
        versions = await mcp.get_tool_versions("add")
        version_strs = [t.version for t in versions]
        assert "2.0" in version_strs
        assert "3.0" in version_strs
        assert "1.0" not in version_strs

    async def test_version_range(self):
        """VersionFilter(version_gte='2.0', version_lt='3.0') shows only v2.x."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.tool(version="1.0")
        def calc() -> int:
            return 1

        @mcp.tool(version="2.0")
        def calc() -> int:
            return 2

        @mcp.tool(version="2.5")
        def calc() -> int:
            return 25

        @mcp.tool(version="3.0")
        def calc() -> int:
            return 3

        mcp.add_transform(VersionFilter(version_gte="2.0", version_lt="3.0"))

        # Should show v2.5 (highest in range)
        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "2.5"

        # Versions in range
        versions = await mcp.get_tool_versions("calc")
        version_strs = [t.version for t in versions]
        assert "2.0" in version_strs
        assert "2.5" in version_strs
        assert "1.0" not in version_strs
        assert "3.0" not in version_strs

    async def test_unversioned_always_passes(self):
        """Unversioned components pass through any filter."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.tool
        def unversioned_tool() -> str:
            return "unversioned"

        @mcp.tool(version="5.0")
        def versioned_tool() -> str:
            return "v5"

        # Filter that would exclude v5.0
        mcp.add_transform(VersionFilter(version_lt="3.0"))

        tools = await mcp.get_tools()
        names = [t.name for t in tools]
        assert "unversioned_tool" in names
        assert "versioned_tool" not in names

    async def test_date_versions(self):
        """Works with date-based versions like '2025-01-15'."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.tool(version="2025-01-01")
        def report() -> str:
            return "jan"

        @mcp.tool(version="2025-06-01")
        def report() -> str:
            return "jun"

        @mcp.tool(version="2025-12-01")
        def report() -> str:
            return "dec"

        # Q1 API: before April
        mcp.add_transform(VersionFilter(version_lt="2025-04-01"))

        tools = await mcp.get_tools()
        assert len(tools) == 1
        assert tools[0].version == "2025-01-01"

    async def test_get_tool_respects_filter(self):
        """get_tool() raises NotFoundError if highest version is filtered out."""
        import pytest

        from fastmcp.exceptions import NotFoundError
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.tool(version="5.0")
        def only_v5() -> str:
            return "v5"

        mcp.add_transform(VersionFilter(version_lt="3.0"))

        # Tool exists but is filtered out
        with pytest.raises(NotFoundError):
            await mcp.get_tool("only_v5")

    async def test_must_specify_at_least_one(self):
        """VersionFilter() with no args raises ValueError."""
        import pytest

        from fastmcp.server.transforms import VersionFilter

        with pytest.raises(ValueError, match="At least one of"):
            VersionFilter()

    async def test_resources_filtered(self):
        """Resources are filtered by version."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.resource("file://config", version="1.0")
        def config_v1() -> str:
            return "v1"

        @mcp.resource("file://config", version="2.0")
        def config_v2() -> str:
            return "v2"

        mcp.add_transform(VersionFilter(version_lt="2.0"))

        resources = await mcp.get_resources()
        assert len(resources) == 1
        assert resources[0].version == "1.0"

    async def test_prompts_filtered(self):
        """Prompts are filtered by version."""
        from fastmcp.server.transforms import VersionFilter

        mcp = FastMCP()

        @mcp.prompt(version="1.0")
        def greet(name: str) -> str:
            return f"Hi {name}"

        @mcp.prompt(version="2.0")
        def greet(name: str) -> str:
            return f"Hello {name}"

        mcp.add_transform(VersionFilter(version_lt="2.0"))

        prompts = await mcp.get_prompts()
        assert len(prompts) == 1
        assert prompts[0].version == "1.0"

    async def test_repr(self):
        """Test VersionFilter string representation."""
        from fastmcp.server.transforms import VersionFilter

        f1 = VersionFilter(version_lt="3.0")
        assert repr(f1) == "VersionFilter(version_lt='3.0')"

        f2 = VersionFilter(version_gte="2.0", version_lt="3.0")
        assert repr(f2) == "VersionFilter(version_gte='2.0', version_lt='3.0')"

        f3 = VersionFilter(version_gte="1.0")
        assert repr(f3) == "VersionFilter(version_gte='1.0')"
