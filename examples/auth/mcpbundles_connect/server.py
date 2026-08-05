"""MCPBundles Connect Auth server example for FastMCP.

Required environment variables:
- MCPBUNDLES_LISTING_SLUG: Published MCPBundles listing slug with Connect Auth

Optional:
- MCPBUNDLES_PUBLIC_CONFIG_BASE_URL: API base (default https://api.mcpbundles.com)
- MCPBUNDLES_REQUIRED_SCOPES: Comma-separated scopes tokens must include
- BASE_URL: Public URL where the FastMCP server is exposed (default http://127.0.0.1:8000/)

To run:
    python server.py
"""

import os

from fastmcp import FastMCP
from fastmcp.server.auth.providers.mcpbundles import (
    McpbundlesConnectProvider,
    connect_auth_callback_identity,
)
from fastmcp.server.dependencies import get_access_token

required_scopes_env = os.getenv("MCPBUNDLES_REQUIRED_SCOPES")
required_scopes = (
    [scope.strip() for scope in required_scopes_env.split(",") if scope.strip()]
    if required_scopes_env
    else None
)

auth = McpbundlesConnectProvider(
    listing_slug=os.environ["MCPBUNDLES_LISTING_SLUG"],
    base_url=os.getenv("BASE_URL", "http://127.0.0.1:8000/"),
    required_scopes=required_scopes,
    public_config_base_url=os.getenv(
        "MCPBUNDLES_PUBLIC_CONFIG_BASE_URL",
        "https://api.mcpbundles.com",
    ),
)

mcp = FastMCP("MCPBundles Connect Auth Example Server", auth=auth)


@mcp.tool
def echo(message: str) -> str:
    """Echo the provided message."""
    return message


@mcp.tool
def get_user_info() -> dict:
    """Return verified Connect Auth identity and authorization metadata."""
    token = get_access_token()
    if token is None:
        return {"error": "Not authenticated"}
    return connect_auth_callback_identity(token)


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
