"""Example usage of the @filterable decorator with JMESPath filtering.

This example shows how to add JMESPath filtering to MCP tools,
allowing clients to reduce response size by filtering/projecting results.
"""

from fastmcp import FastMCP
from fastmcp.contrib.jmespath_tools import ToolResult, filterable

mcp = FastMCP("Example Server")


@mcp.tool
@filterable
async def get_users(limit: int = 100) -> ToolResult:
    """Get users with optional JMESPath filtering.

    Examples:
        # Get all users
        get_users(limit=100)

        # Get just usernames
        get_users(limit=100, jmespath="data.users[*].username")

        # Get only active users
        get_users(limit=100, jmespath="data.users[?status == 'active']")

        # Get summary with count
        get_users(limit=100, jmespath="{count: length(data.users), names: data.users[*].name}")
    """
    # Simulate fetching users from a database
    users = [
        {"id": i, "username": f"user{i}", "name": f"User {i}", "status": "active"}
        for i in range(limit)
    ]
    return {
        "success": True,
        "data": {"users": users, "total": len(users)},
        "error": None,
    }


@mcp.tool
@filterable
async def get_logs(
    level: str | None = None,
    limit: int = 50,
) -> ToolResult:
    """Get application logs with optional JMESPath filtering.

    Examples:
        # Get all logs
        get_logs(limit=50)

        # Get just error messages
        get_logs(jmespath="data.logs[?level == 'ERROR'].message")

        # Get log summary
        get_logs(jmespath="{total: data.count, errors: length(data.logs[?level == 'ERROR'])}")
    """
    # Simulate fetching logs
    levels = ["INFO", "WARNING", "ERROR", "DEBUG"]
    logs = [
        {
            "timestamp": f"2024-01-01T00:00:{i:02d}Z",
            "level": levels[i % 4],
            "message": f"Log message {i}",
        }
        for i in range(limit)
    ]

    if level:
        logs = [log for log in logs if log["level"] == level]

    return {"success": True, "data": {"logs": logs, "count": len(logs)}, "error": None}


if __name__ == "__main__":
    mcp.run()
