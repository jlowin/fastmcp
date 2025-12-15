"""Tests for compensation annotation discovery."""

from fastmcp import FastMCP
from fastmcp.contrib.compensation_annotations import (
    discover_compensation_pairs,
    parse_mcp_schema,
    validate_mcp_schema,
)


class TestParseMcpSchema:
    """Tests for parse_mcp_schema function."""

    def test_parse_from_annotations(self):
        """Parse compensation pair from annotations field."""
        schema = {
            "name": "book_flight",
            "annotations": {"x-compensation-pair": "cancel_flight"},
        }
        result = parse_mcp_schema(schema)
        assert result == ("book_flight", "cancel_flight")

    def test_parse_from_input_schema(self):
        """Parse compensation pair from inputSchema field."""
        schema = {
            "name": "add_item",
            "inputSchema": {
                "type": "object",
                "x-compensation-pair": "delete_item",
            },
        }
        result = parse_mcp_schema(schema)
        assert result == ("add_item", "delete_item")

    def test_parse_from_top_level(self):
        """Parse compensation pair from top-level field."""
        schema = {
            "name": "create_user",
            "x-compensation-pair": "delete_user",
        }
        result = parse_mcp_schema(schema)
        assert result == ("create_user", "delete_user")

    def test_annotations_takes_precedence(self):
        """Annotations field takes precedence over inputSchema."""
        schema = {
            "name": "add_item",
            "annotations": {"x-compensation-pair": "remove_item"},
            "inputSchema": {"x-compensation-pair": "delete_item"},
        }
        result = parse_mcp_schema(schema)
        # annotations is checked first
        assert result == ("add_item", "remove_item")

    def test_returns_none_without_compensation(self):
        """Returns None when no compensation pair is declared."""
        schema = {
            "name": "get_status",
            "description": "Get current status",
        }
        result = parse_mcp_schema(schema)
        assert result is None

    def test_returns_none_without_name(self):
        """Returns None when schema has no name."""
        schema = {
            "annotations": {"x-compensation-pair": "cancel_flight"},
        }
        result = parse_mcp_schema(schema)
        assert result is None

    def test_ignores_non_string_compensation(self):
        """Ignores non-string compensation pair values."""
        schema = {
            "name": "add_item",
            "annotations": {"x-compensation-pair": 123},
        }
        result = parse_mcp_schema(schema)
        assert result is None

    def test_ignores_empty_string_compensation(self):
        """Ignores empty string compensation pair values."""
        schema = {
            "name": "add_item",
            "annotations": {"x-compensation-pair": ""},
        }
        result = parse_mcp_schema(schema)
        assert result is None


class TestDiscoverCompensationPairs:
    """Tests for discover_compensation_pairs function."""

    def test_discover_from_dict_schemas(self):
        """Discover pairs from raw schema dictionaries."""
        tools = [
            {
                "name": "book_flight",
                "annotations": {"x-compensation-pair": "cancel_flight"},
            },
            {"name": "cancel_flight"},
            {
                "name": "book_hotel",
                "annotations": {"x-compensation-pair": "cancel_hotel"},
            },
        ]
        pairs = discover_compensation_pairs(tools)
        assert pairs == {
            "book_flight": "cancel_flight",
            "book_hotel": "cancel_hotel",
        }

    def test_discover_empty_list(self):
        """Returns empty dict for empty tool list."""
        pairs = discover_compensation_pairs([])
        assert pairs == {}

    def test_discover_no_compensation_tools(self):
        """Returns empty dict when no tools have compensation."""
        tools = [
            {"name": "get_status"},
            {"name": "list_items"},
        ]
        pairs = discover_compensation_pairs(tools)
        assert pairs == {}

    async def test_discover_from_fastmcp_tools(self):
        """Discover pairs from FastMCP Tool objects."""
        mcp = FastMCP("TestServer")

        @mcp.tool(annotations={"x-compensation-pair": "delete_item"})
        def add_item(name: str) -> dict:
            return {"id": "123"}

        @mcp.tool
        def delete_item(item_id: str) -> dict:
            return {"deleted": True}

        @mcp.tool(annotations={"x-compensation-pair": "cancel_task"})
        def create_task(title: str) -> dict:
            return {"task_id": "456"}

        tools_dict = await mcp.get_tools()
        tools = list(tools_dict.values())
        pairs = discover_compensation_pairs(tools)

        assert "add_item" in pairs
        assert pairs["add_item"] == "delete_item"
        assert "create_task" in pairs
        assert pairs["create_task"] == "cancel_task"
        # delete_item has no compensation pair
        assert "delete_item" not in pairs


class TestValidateMcpSchema:
    """Tests for validate_mcp_schema function."""

    def test_valid_schema(self):
        """Valid schema returns no errors."""
        schema = {
            "name": "add_item",
            "annotations": {"x-compensation-pair": "delete_item"},
        }
        errors = validate_mcp_schema(schema)
        assert errors == []

    def test_valid_schema_without_compensation(self):
        """Schema without compensation is valid."""
        schema = {
            "name": "get_status",
            "description": "Get status",
        }
        errors = validate_mcp_schema(schema)
        assert errors == []

    def test_missing_name(self):
        """Missing name field is an error."""
        schema = {
            "annotations": {"x-compensation-pair": "delete_item"},
        }
        errors = validate_mcp_schema(schema)
        assert "Missing required field: name" in errors

    def test_empty_name(self):
        """Empty name string is an error."""
        schema = {
            "name": "",
            "annotations": {"x-compensation-pair": "delete_item"},
        }
        errors = validate_mcp_schema(schema)
        assert "Field 'name' must be a non-empty string" in errors

    def test_non_string_name(self):
        """Non-string name is an error."""
        schema = {
            "name": 123,
        }
        errors = validate_mcp_schema(schema)
        assert "Field 'name' must be a non-empty string" in errors

    def test_empty_compensation_in_annotations(self):
        """Empty compensation pair in annotations is an error."""
        schema = {
            "name": "add_item",
            "annotations": {"x-compensation-pair": ""},
        }
        errors = validate_mcp_schema(schema)
        assert (
            "Field 'x-compensation-pair' in annotations must be a non-empty string"
            in errors
        )

    def test_non_string_compensation_in_annotations(self):
        """Non-string compensation pair in annotations is an error."""
        schema = {
            "name": "add_item",
            "annotations": {"x-compensation-pair": 123},
        }
        errors = validate_mcp_schema(schema)
        assert (
            "Field 'x-compensation-pair' in annotations must be a non-empty string"
            in errors
        )

    def test_empty_compensation_in_input_schema(self):
        """Empty compensation pair in inputSchema is an error."""
        schema = {
            "name": "add_item",
            "inputSchema": {"x-compensation-pair": ""},
        }
        errors = validate_mcp_schema(schema)
        assert (
            "Field 'x-compensation-pair' in inputSchema must be a non-empty string"
            in errors
        )

    def test_non_dict_input_schema(self):
        """Non-dict inputSchema is an error."""
        schema = {
            "name": "add_item",
            "inputSchema": "not a dict",
        }
        errors = validate_mcp_schema(schema)
        assert "Field 'inputSchema' must be an object" in errors

    def test_multiple_errors(self):
        """Multiple validation errors are reported."""
        schema = {
            "name": "",
            "annotations": {"x-compensation-pair": ""},
            "inputSchema": "invalid",
        }
        errors = validate_mcp_schema(schema)
        assert len(errors) >= 2


class TestIntegration:
    """Integration tests with FastMCP server."""

    async def test_full_workflow(self):
        """Test complete workflow: create server, add tools, discover pairs."""
        mcp = FastMCP("BookingServer")

        @mcp.tool(
            annotations={
                "x-compensation-pair": "cancel_flight",
                "x-action-type": "create",
            }
        )
        def book_flight(destination: str) -> dict:
            return {"booking_id": "FL-123", "destination": destination}

        @mcp.tool(annotations={"x-action-type": "delete"})
        def cancel_flight(booking_id: str) -> dict:
            return {"cancelled": booking_id}

        @mcp.tool(
            annotations={
                "x-compensation-pair": "cancel_hotel",
                "x-action-type": "create",
            }
        )
        def book_hotel(hotel: str) -> dict:
            return {"reservation_id": "HT-456", "hotel": hotel}

        @mcp.tool(annotations={"x-action-type": "delete"})
        def cancel_hotel(reservation_id: str) -> dict:
            return {"cancelled": reservation_id}

        @mcp.tool(annotations={"x-action-type": "read"})
        def get_bookings() -> list:
            return []

        # Discover compensation pairs
        tools_dict = await mcp.get_tools()
        tools = list(tools_dict.values())
        pairs = discover_compensation_pairs(tools)

        # Verify expected pairs
        assert len(pairs) == 2
        assert pairs["book_flight"] == "cancel_flight"
        assert pairs["book_hotel"] == "cancel_hotel"

        # Verify non-compensatable tools are not included
        assert "cancel_flight" not in pairs
        assert "cancel_hotel" not in pairs
        assert "get_bookings" not in pairs
