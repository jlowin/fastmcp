"""Example FastMCP server for demonstrating Cursor integration."""

from fastmcp import FastMCP

# Create a simple MCP server with name and description
mcp = FastMCP(
    "Cursor Demo Server",
    instructions="A simple demonstration of FastMCP integration with Cursor IDE",
)


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name.

    Args:
        name: The name of the person to greet

    Returns:
        A friendly greeting message
    """
    return f"Hello, {name}! Welcome to FastMCP with Cursor integration! 🎉"


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.

    Args:
        expression: A mathematical expression to evaluate

    Returns:
        The result of the calculation
    """
    try:
        # Note: eval() is used here for demo purposes only
        # In production, use a proper expression parser
        result = eval(expression)
        return f"The result of {expression} is {result}"
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"


if __name__ == "__main__":
    mcp.run()
