"""Example: Compensation Annotations with FastMCP.

This example demonstrates how to use compensation annotations to declare
relationships between tools that create resources and tools that undo them.

Run this example:
    python -m fastmcp.contrib.compensation_annotations.example
"""

import asyncio

from fastmcp import FastMCP
from fastmcp.contrib.compensation_annotations import (
    discover_compensation_pairs,
    parse_mcp_schema,
    validate_mcp_schema,
)

# Create a FastMCP server with compensation-annotated tools
mcp = FastMCP("Booking Server")


@mcp.tool(
    annotations={
        "x-compensation-pair": "cancel_flight",
        "x-action-type": "create",
    }
)
def book_flight(destination: str, date: str) -> dict:
    """Book a flight to a destination."""
    return {
        "booking_id": "FL-12345",
        "destination": destination,
        "date": date,
        "status": "confirmed",
    }


@mcp.tool(annotations={"x-action-type": "delete"})
def cancel_flight(booking_id: str) -> dict:
    """Cancel a flight booking."""
    return {
        "booking_id": booking_id,
        "status": "cancelled",
    }


@mcp.tool(
    annotations={
        "x-compensation-pair": "cancel_hotel",
        "x-action-type": "create",
    }
)
def book_hotel(hotel_name: str, check_in: str, check_out: str) -> dict:
    """Book a hotel room."""
    return {
        "reservation_id": "HT-67890",
        "hotel": hotel_name,
        "check_in": check_in,
        "check_out": check_out,
        "status": "confirmed",
    }


@mcp.tool(annotations={"x-action-type": "delete"})
def cancel_hotel(reservation_id: str) -> dict:
    """Cancel a hotel reservation."""
    return {
        "reservation_id": reservation_id,
        "status": "cancelled",
    }


@mcp.tool(annotations={"x-action-type": "read"})
def get_bookings() -> list:
    """Get all current bookings."""
    return [
        {"type": "flight", "id": "FL-12345"},
        {"type": "hotel", "id": "HT-67890"},
    ]


async def main() -> None:
    """Demonstrate compensation annotation discovery."""
    print("=" * 60)
    print("Compensation Annotations Example")
    print("=" * 60)

    # Get all tools from the server (async method)
    tools_dict = await mcp.get_tools()
    tools = list(tools_dict.values())
    print(f"\nRegistered tools: {[t.name for t in tools]}")

    # Discover compensation pairs
    pairs = discover_compensation_pairs(tools)
    print("\nDiscovered compensation pairs:")
    for tool_name, comp_tool in pairs.items():
        print(f"  {tool_name} -> {comp_tool}")

    # Validate individual schemas
    print("\nSchema validation:")
    for tool in tools:
        schema = {
            "name": tool.name,
            "annotations": (
                tool.annotations.model_dump(exclude_none=True)
                if tool.annotations and hasattr(tool.annotations, "model_dump")
                else {}
            ),
            "inputSchema": tool.parameters,
        }
        errors = validate_mcp_schema(schema)
        status = "valid" if not errors else f"errors: {errors}"
        print(f"  {tool.name}: {status}")

    # Parse a single schema
    print("\nParsing individual schema:")
    example_schema = {
        "name": "add_item",
        "annotations": {"x-compensation-pair": "delete_item"},
    }
    result = parse_mcp_schema(example_schema)
    print(f"  parse_mcp_schema({example_schema})")
    print(f"  -> {result}")


if __name__ == "__main__":
    asyncio.run(main())
