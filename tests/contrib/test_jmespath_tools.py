"""Tests for JMESPath filtering utilities."""

import inspect

from fastmcp.contrib.jmespath_tools import JmespathParam, ToolResult, filterable


class TestFilterableDecorator:
    """Tests for the @filterable decorator."""

    def test_decorator_adds_jmespath_to_signature(self):
        """Decorator adds jmespath parameter to function signature."""

        @filterable
        async def my_tool(limit: int = 10) -> ToolResult:
            return {"success": True, "data": {"items": []}, "error": None}

        sig = inspect.signature(my_tool)
        assert "jmespath" in sig.parameters
        assert sig.parameters["jmespath"].default is None
        assert sig.parameters["jmespath"].annotation == JmespathParam

    def test_decorator_updates_annotations(self):
        """Decorator updates __annotations__ for Pydantic compatibility."""

        @filterable
        async def my_tool(limit: int = 10) -> ToolResult:
            return {"success": True, "data": {"items": []}, "error": None}

        assert "jmespath" in my_tool.__annotations__
        assert my_tool.__annotations__["jmespath"] == JmespathParam
        assert my_tool.__annotations__["return"] == ToolResult

    async def test_without_filter_returns_original(self):
        """Without jmespath filter, returns original ToolResult."""

        @filterable
        async def my_tool(limit: int = 10) -> ToolResult:
            items = [{"id": i, "name": f"item-{i}"} for i in range(limit)]
            return {
                "success": True,
                "data": {"count": limit, "items": items},
                "error": None,
            }

        result = await my_tool(limit=3)
        assert result["success"] is True
        assert result["data"]["count"] == 3
        assert len(result["data"]["items"]) == 3
        assert result["error"] is None

    async def test_with_filter_transforms_data(self):
        """With jmespath filter, transforms the data field."""

        @filterable
        async def my_tool(limit: int = 10) -> ToolResult:
            items = [{"id": i, "name": f"item-{i}"} for i in range(limit)]
            return {
                "success": True,
                "data": {"count": limit, "items": items},
                "error": None,
            }

        # Extract just names - note the filter operates on entire result
        result = await my_tool(limit=3, jmespath="data.items[*].name")
        assert result["success"] is True
        assert result["data"] == ["item-0", "item-1", "item-2"]
        assert result["error"] is None

    async def test_filter_with_condition(self):
        """Filter can apply conditions."""

        @filterable
        async def my_tool() -> ToolResult:
            items = [
                {"id": 1, "status": "active"},
                {"id": 2, "status": "inactive"},
                {"id": 3, "status": "active"},
            ]
            return {"success": True, "data": {"items": items}, "error": None}

        result = await my_tool(jmespath="data.items[?status == 'active']")
        assert result["success"] is True
        assert len(result["data"]) == 2
        assert all(item["status"] == "active" for item in result["data"])

    async def test_filter_with_projection(self):
        """Filter can create projections."""

        @filterable
        async def my_tool() -> ToolResult:
            items = [{"id": 1}, {"id": 2}, {"id": 3}]
            return {
                "success": True,
                "data": {"count": 3, "items": items},
                "error": None,
            }

        result = await my_tool(jmespath="{total: data.count, ids: data.items[*].id}")
        assert result["success"] is True
        assert result["data"] == {"total": 3, "ids": [1, 2, 3]}

    async def test_invalid_filter_returns_error(self):
        """Invalid jmespath expression returns error."""

        @filterable
        async def my_tool() -> ToolResult:
            return {"success": True, "data": {"items": []}, "error": None}

        result = await my_tool(jmespath="[*.bad.syntax")
        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] is not None
        assert "JMESPath error" in result["error"]

    async def test_filter_on_failed_result_passthrough(self):
        """If original result is not successful, filter is not applied."""

        @filterable
        async def my_tool() -> ToolResult:
            return {"success": False, "data": None, "error": "Something went wrong"}

        result = await my_tool(jmespath="data.items[*].name")
        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] == "Something went wrong"

    def test_sync_wrapper_works(self):
        """Decorator works with sync functions too."""

        @filterable
        def my_tool(limit: int = 10) -> ToolResult:
            items = [{"id": i} for i in range(limit)]
            return {"success": True, "data": {"items": items}, "error": None}

        # Without filter
        result = my_tool(limit=2)
        assert result["success"] is True
        assert len(result["data"]["items"]) == 2

        # With filter
        result = my_tool(limit=2, jmespath="data.items[*].id")
        assert result["data"] == [0, 1]

    async def test_filter_extracts_nested_field(self):
        """Filter can extract deeply nested fields."""

        @filterable
        async def my_tool() -> ToolResult:
            return {
                "success": True,
                "data": {
                    "response": {
                        "users": [
                            {"profile": {"name": "Alice"}},
                            {"profile": {"name": "Bob"}},
                        ]
                    }
                },
                "error": None,
            }

        result = await my_tool(jmespath="data.response.users[*].profile.name")
        assert result["success"] is True
        assert result["data"] == ["Alice", "Bob"]

    async def test_filter_with_length_function(self):
        """Filter can use JMESPath built-in functions."""

        @filterable
        async def my_tool() -> ToolResult:
            items = [{"id": i} for i in range(5)]
            return {"success": True, "data": {"items": items}, "error": None}

        result = await my_tool(jmespath="length(data.items)")
        assert result["success"] is True
        assert result["data"] == 5


class TestToolResult:
    """Tests for the ToolResult TypedDict."""

    def test_tool_result_structure(self):
        """ToolResult has the expected structure."""
        result: ToolResult = {"success": True, "data": {"key": "value"}, "error": None}

        assert result["success"] is True
        assert result["data"] == {"key": "value"}
        assert result["error"] is None

    def test_tool_result_error_case(self):
        """ToolResult can represent errors."""
        result: ToolResult = {"success": False, "data": None, "error": "Error message"}

        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] == "Error message"


class TestJmespathImportError:
    """Tests for jmespath import error handling."""

    def test_jmespath_import_works(self):
        """Verify jmespath is available in test environment."""
        from fastmcp.contrib.jmespath_tools.jmespath_tools import _get_jmespath

        jmespath = _get_jmespath()
        assert jmespath is not None
        # Test basic functionality
        result = jmespath.search("a.b", {"a": {"b": "value"}})
        assert result == "value"
