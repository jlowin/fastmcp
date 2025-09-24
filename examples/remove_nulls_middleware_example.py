#!/usr/bin/env python3
"""
Example middleware for removing null values from tool call structured content.

This middleware demonstrates how to post-process tool responses to remove null
values from structured_content, which can help reduce token count in responses.
"""

from typing import Any

import mcp.types as mt

from fastmcp import Client, FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult


def remove_nulls(data: Any) -> Any:
    """
    Recursively remove null values from data structures.

    Args:
        data: The data structure to clean (dict, list, or primitive)

    Returns:
        The cleaned data structure with null values removed
    """
    if isinstance(data, dict):
        # Remove keys with None values and recursively clean remaining values
        return {
            key: remove_nulls(value) for key, value in data.items() if value is not None
        }
    elif isinstance(data, list):
        # Recursively clean list items, filtering out None values
        return [remove_nulls(item) for item in data if item is not None]
    else:
        # Return primitive values as-is
        return data


class RemoveNullsMiddleware(Middleware):
    """
    Middleware that removes null values from tool call structured content.

    This middleware intercepts tool call responses and removes null values
    from the structured_content field, which can help reduce token usage
    in responses.

    Example:
        ```python
        from fastmcp import FastMCP
        from remove_nulls_middleware_example import RemoveNullsMiddleware

        mcp = FastMCP("MyServer")
        mcp.add_middleware(RemoveNullsMiddleware())

        @mcp.tool
        def get_user(name: str) -> dict:
            return {
                "name": name,
                "email": None,  # This will be removed
                "age": 25,
                "address": None,  # This will be removed
                "preferences": {
                    "theme": "dark",
                    "notifications": None  # This will be removed
                }
            }
        ```
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """
        Intercept tool calls and remove nulls from structured content.

        Args:
            context: The middleware context containing the tool call request
            call_next: Function to call the next middleware or the actual tool

        Returns:
            ToolResult with nulls removed from structured_content
        """
        # Call the next middleware or the tool itself
        result = await call_next(context)

        # If there's structured content, remove nulls from it
        if result.structured_content is not None:
            cleaned_content = remove_nulls(result.structured_content)
            # Create a new ToolResult with cleaned structured content
            result = ToolResult(
                content=result.content, structured_content=cleaned_content
            )

        return result


# Example usage and demonstration
if __name__ == "__main__":
    import asyncio

    # Create a FastMCP server with the remove nulls middleware
    mcp = FastMCP("NullRemovalExample")
    mcp.add_middleware(RemoveNullsMiddleware())

    @mcp.tool
    def get_user_profile(user_id: int) -> dict:
        """Get user profile with potentially null fields."""
        return {
            "id": user_id,
            "name": "John Doe",
            "email": "john@example.com" if user_id == 1 else None,
            "age": 30,
            "phone": None,
            "address": {
                "street": "123 Main St" if user_id == 1 else None,
                "city": "Anytown",
                "zip": None,
                "country": "USA",
            },
            "preferences": {"theme": "dark", "notifications": None, "language": "en"},
            "metadata": None,
        }

    @mcp.tool
    def get_product_list() -> dict:
        """Get a list of products with optional fields."""
        return {
            "products": [
                {
                    "id": 1,
                    "name": "Widget A",
                    "price": 19.99,
                    "description": None,
                    "category": "widgets",
                    "in_stock": True,
                    "sale_price": None,
                },
                {
                    "id": 2,
                    "name": "Widget B",
                    "price": 29.99,
                    "description": "A great widget",
                    "category": "widgets",
                    "in_stock": False,
                    "sale_price": 24.99,
                },
            ],
            "total_count": 2,
            "next_page": None,
        }

    async def demonstrate_null_removal():
        """Demonstrate the null removal middleware in action."""
        print("=== FastMCP Null Removal Middleware Example ===\n")

        # Connect to the server using in-memory transport
        async with Client(mcp) as client:
            print("1. Calling get_user_profile with user_id=1:")
            result1 = await client.call_tool("get_user_profile", {"user_id": 1})
            print(f"   Structured content: {result1.structured_content}")
            print()

            print("2. Calling get_user_profile with user_id=2 (more nulls):")
            result2 = await client.call_tool("get_user_profile", {"user_id": 2})
            print(f"   Structured content: {result2.structured_content}")
            print()

            print("3. Calling get_product_list:")
            result3 = await client.call_tool("get_product_list", {})
            print(f"   Structured content: {result3.structured_content}")
            print()

            print(
                "Notice how all null values have been removed from the structured content!"
            )
            print(
                "This reduces the response size and token count while preserving the data structure."
            )

    # Run the demonstration
    asyncio.run(demonstrate_null_removal())
