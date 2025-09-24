from examples.remove_nulls_middleware_example import RemoveNullsMiddleware, remove_nulls
from fastmcp import Client, FastMCP


def test_remove_nulls_dict():
    """Test removing nulls from dictionary structures."""
    data = {
        "name": "John",
        "age": None,
        "email": "john@example.com",
        "phone": None,
        "nested": {"key1": "value1", "key2": None, "key3": "value3"},
    }

    expected = {
        "name": "John",
        "email": "john@example.com",
        "nested": {"key1": "value1", "key3": "value3"},
    }

    result = remove_nulls(data)
    assert result == expected


def test_remove_nulls_list():
    """Test removing nulls from list structures."""
    data = [1, None, "hello", None, {"key": None, "valid": "data"}]
    expected = [1, "hello", {"valid": "data"}]

    result = remove_nulls(data)
    assert result == expected


def test_remove_nulls_primitive():
    """Test that primitive values are returned unchanged."""
    assert remove_nulls("hello") == "hello"
    assert remove_nulls(42) == 42
    assert remove_nulls(True) is True
    assert remove_nulls(None) is None


def test_remove_nulls_complex_nested():
    """Test removing nulls from complex nested structures."""
    data = {
        "users": [
            {
                "id": 1,
                "name": "Alice",
                "email": None,
                "preferences": {"theme": "dark", "notifications": None},
            },
            None,  # This entire user should be removed
            {
                "id": 2,
                "name": "Bob",
                "email": "bob@example.com",
                "preferences": None,  # This should be removed
            },
        ],
        "metadata": None,
        "total": 2,
    }

    expected = {
        "users": [
            {"id": 1, "name": "Alice", "preferences": {"theme": "dark"}},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ],
        "total": 2,
    }

    result = remove_nulls(data)
    assert result == expected


async def test_middleware_removes_nulls_from_tool_result():
    """Test that the middleware removes nulls from tool results."""
    mcp = FastMCP("TestServer")
    mcp.add_middleware(RemoveNullsMiddleware())

    @mcp.tool
    def test_tool() -> dict:
        return {
            "name": "test",
            "value": None,
            "data": {"key1": "value1", "key2": None},
            "list": [1, None, 3],
        }

    async with Client(mcp) as client:
        result = await client.call_tool("test_tool", {})

        expected_structured_content = {
            "name": "test",
            "data": {"key1": "value1"},
            "list": [1, 3],
        }

        assert result.structured_content == expected_structured_content


async def test_middleware_preserves_non_null_content():
    """Test that the middleware preserves content without nulls."""
    mcp = FastMCP("TestServer")
    mcp.add_middleware(RemoveNullsMiddleware())

    @mcp.tool
    def test_tool() -> dict:
        return {
            "name": "test",
            "value": 42,
            "data": {"key1": "value1", "key2": "value2"},
        }

    async with Client(mcp) as client:
        result = await client.call_tool("test_tool", {})

        expected_structured_content = {
            "name": "test",
            "value": 42,
            "data": {"key1": "value1", "key2": "value2"},
        }

        assert result.structured_content == expected_structured_content


async def test_middleware_handles_none_structured_content():
    """Test that the middleware handles tools with no structured content."""
    mcp = FastMCP("TestServer")
    mcp.add_middleware(RemoveNullsMiddleware())

    @mcp.tool
    def text_only_tool() -> str:
        return "This tool returns only text content"

    async with Client(mcp) as client:
        result = await client.call_tool("text_only_tool", {})

        # Should work without error and preserve the text content
        assert "This tool returns only text content" in str(result.content)
