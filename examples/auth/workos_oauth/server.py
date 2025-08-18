"""WorkOS OAuth server example for FastMCP.

This example demonstrates how to protect a FastMCP server with WorkOS OAuth.

Required environment variables:
- FASTMCP_SERVER_AUTH_WORKOS_CLIENT_ID: Your WorkOS client ID
- FASTMCP_SERVER_AUTH_WORKOS_CLIENT_SECRET: Your WorkOS client secret

Optional:
- FASTMCP_SERVER_AUTH_WORKOS_ORGANIZATION_ID: For SSO with specific org
- FASTMCP_SERVER_AUTH_WORKOS_CONNECTION_ID: For SSO with specific connection

To run:
    python server.py
"""

import os

from fastmcp import FastMCP
from fastmcp.server.auth.providers.workos import WorkOSProvider

auth = WorkOSProvider(
    client_id=os.getenv("WORKOS_CLIENT_ID") or "",
    client_secret=os.getenv("WORKOS_API_KEY") or "",
    base_url="http://localhost:8000",
    organization_id=os.getenv("WORKOS_ORGANIZATION_ID"),  # Required for SSO
    # connection_id=os.getenv("WORKOS_CONNECTION_ID"),  # Alternative to organization_id
    # redirect_path="/oauth/callback",  # Default path - change if using a different callback URL
)

mcp = FastMCP("WorkOS OAuth Example Server", auth=auth)


@mcp.tool
def echo(message: str) -> str:
    """Echo the provided message."""
    return message


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
