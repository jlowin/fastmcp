"""Middleware for bulk tool calling functionality."""

from typing import Annotated

from mcp.types import TextContent

from fastmcp.server.context import Context
from fastmcp.server.middleware.bulk_tool_caller_types import (
    CallToolRequest,
    CallToolRequestResult,
)
from fastmcp.server.middleware.tool_injection import ToolInjectionMiddleware
from fastmcp.tools.tool import Tool


async def call_tools_bulk(
    context: Context,
    tool_calls: Annotated[
        list[CallToolRequest],
        "List of tool calls to execute. Each call can be for a different tool with different arguments.",
    ],
    continue_on_error: Annotated[
        bool,
        "If True, continue executing remaining tools even if one fails. If False, stop on first error.",
    ] = True,
) -> list[CallToolRequestResult]:
    """Call multiple tools registered on this MCP server in a single request.

    Each call can be for a different tool and can include different arguments.
    Useful for speeding up what would otherwise take several individual tool calls.

    Args:
        context: The request context providing access to the server
        tool_calls: List of tool calls to execute
        continue_on_error: Whether to continue on errors (default: True)

    Returns:
        List of results, one per tool call
    """
    results = []

    for tool_call in tool_calls:
        try:
            # Call the tool directly through the tool manager
            tool_result = await context.fastmcp._tool_manager.call_tool(
                key=tool_call.tool, arguments=tool_call.arguments
            )

            # Convert ToolResult to CallToolRequestResult, preserving all fields
            # Note: ToolResult doesn't have isError - it's only on CallToolResult
            # For successful calls, we don't set isError (defaults to None)
            results.append(
                CallToolRequestResult(
                    tool=tool_call.tool,
                    arguments=tool_call.arguments,
                    content=tool_result.content,
                    structuredContent=tool_result.structured_content,
                )
            )
        except Exception as e:
            # Create error result
            error_message = f"Error calling tool '{tool_call.tool}': {e}"
            results.append(
                CallToolRequestResult(
                    tool=tool_call.tool,
                    arguments=tool_call.arguments,
                    isError=True,
                    content=[TextContent(text=error_message, type="text")],
                )
            )

            if not continue_on_error:
                break

    return results


async def call_tool_bulk(
    context: Context,
    tool: Annotated[str, "The name of the tool to call multiple times."],
    tool_arguments: Annotated[
        list[dict[str, str | int | float | bool | None]],
        "List of argument dictionaries. Each dictionary contains the arguments for one tool invocation.",
    ],
    continue_on_error: Annotated[
        bool,
        "If True, continue executing remaining calls even if one fails. If False, stop on first error.",
    ] = True,
) -> list[CallToolRequestResult]:
    """Call a single tool registered on this MCP server multiple times with a single request.

    Each call can include different arguments. Useful for speeding up what would
    otherwise take several individual tool calls.

    Args:
        context: The request context providing access to the server
        tool: The name of the tool to call
        tool_arguments: List of argument dictionaries for each invocation
        continue_on_error: Whether to continue on errors (default: True)

    Returns:
        List of results, one per invocation
    """
    results = []

    for args in tool_arguments:
        try:
            # Call the tool directly through the tool manager
            tool_result = await context.fastmcp._tool_manager.call_tool(
                key=tool, arguments=args
            )

            # Convert ToolResult to CallToolRequestResult, preserving all fields
            # Note: ToolResult doesn't have isError - it's only on CallToolResult
            # For successful calls, we don't set isError (defaults to None)
            results.append(
                CallToolRequestResult(
                    tool=tool,
                    arguments=args,
                    content=tool_result.content,
                    structuredContent=tool_result.structured_content,
                )
            )
        except Exception as e:
            # Create error result
            error_message = f"Error calling tool '{tool}': {e}"
            results.append(
                CallToolRequestResult(
                    tool=tool,
                    arguments=args,
                    isError=True,
                    content=[TextContent(text=error_message, type="text")],
                )
            )

            if not continue_on_error:
                break

    return results


class BulkToolCallerMiddleware(ToolInjectionMiddleware):
    """Middleware for injecting bulk tool calling capabilities into the server.

    This middleware adds two tools to the server:
    - call_tools_bulk: Call multiple different tools in a single request
    - call_tool_bulk: Call a single tool multiple times with different arguments

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.middleware import BulkToolCallerMiddleware

        mcp = FastMCP("MyServer", middleware=[BulkToolCallerMiddleware()])

        @mcp.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @mcp.tool
        def add(a: int, b: int) -> int:
            return a + b
        ```

        Now clients can use bulk calling:
        ```python
        # Call multiple different tools
        result = await client.call_tool("call_tools_bulk", {
            "tool_calls": [
                {"tool": "greet", "arguments": {"name": "Alice"}},
                {"tool": "add", "arguments": {"a": 1, "b": 2}}
            ]
        })

        # Call same tool multiple times
        result = await client.call_tool("call_tool_bulk", {
            "tool": "greet",
            "tool_arguments": [
                {"name": "Alice"},
                {"name": "Bob"}
            ]
        })
        ```
    """

    def __init__(self) -> None:
        """Initialize the bulk tool caller middleware."""
        tools: list[Tool] = [
            Tool.from_function(call_tools_bulk),
            Tool.from_function(call_tool_bulk),
        ]
        super().__init__(tools=tools)
