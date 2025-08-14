#!/usr/bin/env python
"""Demo server for testing inspect command."""

from fastmcp import FastMCP

# Create a server with some components
mcp = FastMCP(
    "DemoServer",
    instructions="A demo server for testing inspect command",
    version="2.5.0",
)


@mcp.tool
def calculate(x: int, y: int, operation: str = "add") -> dict:
    """Perform calculations on two numbers."""
    if operation == "add":
        result = x + y
    elif operation == "multiply":
        result = x * y
    else:
        result = 0
    return {"result": result, "operation": operation}


@mcp.resource("resource://config")
def get_config() -> str:
    """Get configuration data."""
    return "Config data here"


@mcp.prompt
def math_prompt(problem: str) -> list:
    """Generate a math problem prompt."""
    return [{"role": "user", "content": f"Solve this math problem: {problem}"}]
