#!/usr/bin/env python
"""Demo v1 server for testing inspect command."""

from mcp.server.fastmcp import FastMCP as FastMCP1x

# Create a v1 server
mcp = FastMCP1x("DemoV1Server")


@mcp.tool()
def multiply(x: int, y: int) -> int:
    """Multiply two numbers."""
    return x * y


@mcp.resource("resource://data")
def get_data() -> str:
    """Get some data."""
    return "v1 data"
