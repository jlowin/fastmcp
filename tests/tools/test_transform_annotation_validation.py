"""Test that TransformedTool validates return type annotations (Issue #1369)."""

import pytest

from fastmcp.tools import Tool, forward
from fastmcp.tools.tool_transform import ArgTransform


def test_transform_function_without_return_annotation_raises_error():
    """Test that transform functions without return annotations raise a clear error."""

    # Create a simple tool
    def original_tool(x: int, y: int) -> str:
        return f"Result: {x + y}"

    original = Tool.from_function(original_tool)

    # Transform function WITHOUT return type annotation
    async def transform_no_annotation(a: int, b: int):  # Missing -> annotation
        result = await forward(a=a, b=b)
        return f"Transformed: {result}"

    # Should raise ValueError with helpful message
    with pytest.raises(ValueError) as exc_info:
        Tool.from_tool(
            original,
            transform_fn=transform_no_annotation,
            transform_args={"x": ArgTransform(name="a"), "y": ArgTransform(name="b")},
        )

    error_msg = str(exc_info.value)
    assert "missing a return type annotation" in error_msg
    assert "transform_no_annotation" in error_msg
    assert "-> str" in error_msg or "-> dict" in error_msg  # Helpful examples


def test_transform_function_with_return_annotation_works():
    """Test that transform functions with return annotations work correctly."""

    # Create a simple tool
    def original_tool(x: int, y: int) -> str:
        return f"Result: {x + y}"

    original = Tool.from_function(original_tool)

    # Transform function WITH return type annotation
    async def transform_with_annotation(a: int, b: int) -> str:
        result = await forward(a=a, b=b)
        return f"Transformed: {result}"

    # Should work without errors
    transformed = Tool.from_tool(
        original,
        transform_fn=transform_with_annotation,
        transform_args={"x": ArgTransform(name="a"), "y": ArgTransform(name="b")},
    )

    assert transformed is not None
    # The tool name defaults to the parent's name, not the transform function's name
    assert transformed.name == "original_tool"
    assert "a" in transformed.parameters["properties"]
    assert "b" in transformed.parameters["properties"]


def test_transform_function_with_tool_result_annotation_works():
    """Test that transform functions returning ToolResult work correctly."""
    from mcp.types import TextContent

    from fastmcp.tools.tool import ToolResult

    # Create a simple tool
    def original_tool(x: int, y: int) -> str:
        return f"Result: {x + y}"

    original = Tool.from_function(original_tool)

    # Transform function that returns ToolResult
    async def transform_with_tool_result(a: int, b: int) -> ToolResult:
        result = await forward(a=a, b=b)
        return ToolResult(
            content=[TextContent(type="text", text=f"Custom: {result}")],
            structured_content={"custom": True},
        )

    # Should work without errors
    transformed = Tool.from_tool(
        original,
        transform_fn=transform_with_tool_result,
        transform_args={"x": ArgTransform(name="a"), "y": ArgTransform(name="b")},
    )

    assert transformed is not None
    assert transformed.output_schema is None  # ToolResult return type disables schema


def test_pure_transformation_without_custom_function_works():
    """Test that pure transformations (no custom function) still work."""

    # Create a simple tool
    def original_tool(x: int, y: int) -> str:
        return f"Result: {x + y}"

    original = Tool.from_function(original_tool)

    # Pure transformation without custom function
    transformed = Tool.from_tool(
        original,
        transform_args={"x": ArgTransform(name="a"), "y": ArgTransform(name="b")},
    )

    assert transformed is not None
    assert "a" in transformed.parameters["properties"]
    assert "b" in transformed.parameters["properties"]
    # Should inherit parent's output schema
    assert transformed.output_schema == original.output_schema
