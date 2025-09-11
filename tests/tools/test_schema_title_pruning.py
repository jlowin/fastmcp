"""Tests for title pruning in tool input and output schemas."""

from pydantic import BaseModel

from fastmcp import FastMCP
from fastmcp.client import Client


class InputModel(BaseModel):
    """A model with titles to test input schema pruning."""

    name: str
    age: int


class OutputModel(BaseModel):
    """A model with titles to test output schema pruning."""

    name: str
    age: int


def has_titles(obj):
    """Recursively check if a schema contains any title fields."""
    if isinstance(obj, dict):
        if "title" in obj:
            return True
        return any(has_titles(v) for v in obj.values())
    elif isinstance(obj, list):
        return any(has_titles(item) for item in obj)
    return False


class TestSchemaTitlePruning:
    """Test that titles are pruned from tool schemas."""

    def test_output_schema_titles_pruned(self):
        """Test that titles are pruned from output schemas."""
        server = FastMCP("test")

        @server.tool
        def get_test_output() -> OutputModel:
            """Tool that returns a model with titles."""
            return OutputModel(name="test", age=25)

        async def check():
            async with Client(server) as client:
                tools = await client.list_tools()
                tool = next(t for t in tools if t.name == "get_test_output")

                # Output schema should exist but not contain titles
                assert tool.outputSchema is not None
                assert not has_titles(tool.outputSchema), (
                    f"Output schema contains titles: {tool.outputSchema}"
                )

                # Verify the schema still contains the expected structure
                assert tool.outputSchema.get("type") == "object"
                assert "properties" in tool.outputSchema
                assert "name" in tool.outputSchema["properties"]
                assert "age" in tool.outputSchema["properties"]

        # Use pytest-asyncio's event loop
        import asyncio

        asyncio.run(check())

    def test_input_schema_titles_pruned(self):
        """Test that titles are pruned from input schemas."""
        server = FastMCP("test")

        @server.tool
        def process_test_input(data: InputModel) -> str:
            """Tool that takes a model with titles as input."""
            return f"Processed {data.name}, age {data.age}"

        async def check():
            async with Client(server) as client:
                tools = await client.list_tools()
                tool = next(t for t in tools if t.name == "process_test_input")

                # Input schema should not contain titles
                assert not has_titles(tool.inputSchema), (
                    f"Input schema contains titles: {tool.inputSchema}"
                )

                # Verify the schema still contains the expected structure
                assert tool.inputSchema.get("type") == "object"
                assert "properties" in tool.inputSchema
                assert "data" in tool.inputSchema["properties"]

                # Check that the model definition in $defs also has no titles
                if "$defs" in tool.inputSchema:
                    assert not has_titles(tool.inputSchema["$defs"])

        import asyncio

        asyncio.run(check())

    def test_simple_types_unaffected(self):
        """Test that tools with simple types still work correctly."""
        server = FastMCP("test")

        @server.tool
        def simple_tool(name: str, age: int) -> str:
            """Tool with simple parameter types."""
            return f"{name} is {age} years old"

        async def check():
            async with Client(server) as client:
                tools = await client.list_tools()
                tool = next(t for t in tools if t.name == "simple_tool")

                # Should not contain titles
                assert not has_titles(tool.inputSchema)

                # Verify basic structure
                assert tool.inputSchema.get("type") == "object"
                assert "properties" in tool.inputSchema
                assert "name" in tool.inputSchema["properties"]
                assert "age" in tool.inputSchema["properties"]

        import asyncio

        asyncio.run(check())
