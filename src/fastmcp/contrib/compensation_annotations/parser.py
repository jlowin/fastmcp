"""Compensation annotation parsing for MCP tool schemas.

This module provides functions to parse MCP tool schemas and discover
compensation pairs from the `x-compensation-pair` annotation.

Compensation pairs define relationships between tools that create resources
and tools that undo those creations, enabling automatic rollback in
transactional agent workflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fastmcp.tools.tool import Tool

logger = get_logger(__name__)


def parse_mcp_schema(schema: dict[str, Any]) -> tuple[str, str] | None:
    """Extract compensation pair from an MCP tool schema.

    Searches for `x-compensation-pair` in multiple locations within the schema:
    1. `annotations["x-compensation-pair"]` (recommended)
    2. `inputSchema["x-compensation-pair"]`
    3. Top-level `x-compensation-pair`

    Args:
        schema: MCP tool schema dictionary with at least a "name" field.

    Returns:
        Tuple of (tool_name, compensation_tool_name) if found, None otherwise.

    Example:
        >>> schema = {
        ...     "name": "book_flight",
        ...     "annotations": {"x-compensation-pair": "cancel_flight"}
        ... }
        >>> parse_mcp_schema(schema)
        ('book_flight', 'cancel_flight')

        >>> schema = {"name": "get_status"}  # No compensation
        >>> parse_mcp_schema(schema)
        None
    """
    tool_name = schema.get("name")
    if not tool_name:
        return None

    # Check annotations (recommended location)
    annotations = schema.get("annotations", {})
    if isinstance(annotations, dict):
        comp_pair = annotations.get("x-compensation-pair")
        if comp_pair and isinstance(comp_pair, str):
            return (tool_name, comp_pair)

    # Check inputSchema for x-compensation-pair
    input_schema = schema.get("inputSchema", {})
    if isinstance(input_schema, dict):
        comp_pair = input_schema.get("x-compensation-pair")
        if comp_pair and isinstance(comp_pair, str):
            return (tool_name, comp_pair)

    # Check top-level x-compensation-pair
    comp_pair = schema.get("x-compensation-pair")
    if comp_pair and isinstance(comp_pair, str):
        return (tool_name, comp_pair)

    return None


def discover_compensation_pairs(
    tools: Iterable[Tool] | Iterable[dict[str, Any]],
) -> dict[str, str]:
    """Discover compensation pairs from a collection of tools.

    Scans tool schemas for `x-compensation-pair` annotations and returns
    a mapping of tool names to their compensation tool names.

    Args:
        tools: Iterable of FastMCP Tool objects or raw schema dictionaries.

    Returns:
        Dictionary mapping tool names to their compensation tool names.

    Example:
        >>> from fastmcp import FastMCP
        >>> mcp = FastMCP("Server")
        >>>
        >>> @mcp.tool(annotations={"x-compensation-pair": "cancel_flight"})
        ... def book_flight(dest: str) -> dict:
        ...     return {"booking_id": "123"}
        >>>
        >>> @mcp.tool(annotations={"x-compensation-pair": "cancel_hotel"})
        ... def book_hotel(hotel: str) -> dict:
        ...     return {"reservation_id": "456"}
        >>>
        >>> pairs = discover_compensation_pairs(mcp._tool_manager.tools.values())
        >>> # Returns: {"book_flight": "cancel_flight", "book_hotel": "cancel_hotel"}
    """
    pairs: dict[str, str] = {}

    for tool in tools:
        schema = _get_tool_schema(tool)
        if schema:
            result = parse_mcp_schema(schema)
            if result:
                tool_name, comp_tool = result
                pairs[tool_name] = comp_tool
                logger.debug(
                    f"Discovered compensation pair: {tool_name} -> {comp_tool}"
                )

    return pairs


def _get_tool_schema(tool: Any) -> dict[str, Any] | None:
    """Extract a schema dictionary from a tool object.

    Supports:
    - Raw schema dictionaries (passed through)
    - FastMCP Tool objects
    - Objects with name/get_input_schema protocol
    - LangChain-style tools with args_schema

    Args:
        tool: A tool object or schema dictionary.

    Returns:
        Schema dictionary or None if extraction fails.
    """
    if isinstance(tool, dict):
        return tool

    # FastMCP Tool object
    if (
        hasattr(tool, "name")
        and hasattr(tool, "parameters")
        and hasattr(tool, "annotations")
    ):
        annotations_dict: dict[str, Any] = {}
        if tool.annotations is not None:
            # ToolAnnotations is a Pydantic model, convert to dict
            if hasattr(tool.annotations, "model_dump"):
                annotations_dict = tool.annotations.model_dump(exclude_none=True)
            elif hasattr(tool.annotations, "dict"):
                annotations_dict = tool.annotations.dict(exclude_none=True)
            elif isinstance(tool.annotations, dict):
                annotations_dict = tool.annotations
            # Also include any extra fields that might be in the annotations
            if hasattr(tool.annotations, "__dict__"):
                for key, value in tool.annotations.__dict__.items():
                    if not key.startswith("_") and value is not None:
                        annotations_dict[key] = value

        return {
            "name": tool.name,
            "description": getattr(tool, "description", ""),
            "inputSchema": tool.parameters,
            "annotations": annotations_dict,
        }

    # Generic protocol: name + get_input_schema
    if hasattr(tool, "name") and hasattr(tool, "get_input_schema"):
        try:
            return {
                "name": tool.name,
                "description": getattr(tool, "description", ""),
                "inputSchema": tool.get_input_schema(),
            }
        except Exception:
            pass

    # LangChain-style tool with args_schema
    if hasattr(tool, "name") and hasattr(tool, "args_schema"):
        try:
            args_schema = tool.args_schema
            if args_schema and hasattr(args_schema, "model_json_schema"):
                return {
                    "name": tool.name,
                    "description": getattr(tool, "description", ""),
                    "inputSchema": args_schema.model_json_schema(),
                }
            elif args_schema and hasattr(args_schema, "schema"):
                return {
                    "name": tool.name,
                    "description": getattr(tool, "description", ""),
                    "inputSchema": args_schema.schema(),
                }
        except Exception:
            pass

    return None


def validate_mcp_schema(schema: dict[str, Any]) -> list[str]:
    """Validate an MCP tool schema for compensation annotation correctness.

    Checks that:
    1. Schema has the required "name" field
    2. The name is a non-empty string
    3. If `x-compensation-pair` is declared, it's a valid non-empty string

    Args:
        schema: MCP tool schema dictionary to validate.

    Returns:
        List of validation error messages. Empty list if valid.

    Example:
        >>> schema = {"name": "add_item", "annotations": {"x-compensation-pair": ""}}
        >>> errors = validate_mcp_schema(schema)
        >>> # Returns: ["Field 'x-compensation-pair' must be a non-empty string"]
    """
    errors: list[str] = []

    # Check required name field
    if "name" not in schema:
        errors.append("Missing required field: name")
        return errors

    tool_name = schema["name"]
    if not isinstance(tool_name, str) or not tool_name:
        errors.append("Field 'name' must be a non-empty string")

    # Validate x-compensation-pair in annotations
    annotations = schema.get("annotations", {})
    if isinstance(annotations, dict):
        comp_pair = annotations.get("x-compensation-pair")
        if comp_pair is not None:
            if not isinstance(comp_pair, str) or not comp_pair:
                errors.append(
                    "Field 'x-compensation-pair' in annotations must be a non-empty string"
                )

    # Validate x-compensation-pair in inputSchema
    input_schema = schema.get("inputSchema")
    if input_schema is not None:
        if not isinstance(input_schema, dict):
            errors.append("Field 'inputSchema' must be an object")
        else:
            comp_pair = input_schema.get("x-compensation-pair")
            if comp_pair is not None:
                if not isinstance(comp_pair, str) or not comp_pair:
                    errors.append(
                        "Field 'x-compensation-pair' in inputSchema must be a non-empty string"
                    )

    # Validate top-level x-compensation-pair
    comp_pair = schema.get("x-compensation-pair")
    if comp_pair is not None:
        if not isinstance(comp_pair, str) or not comp_pair:
            errors.append("Field 'x-compensation-pair' must be a non-empty string")

    return errors
