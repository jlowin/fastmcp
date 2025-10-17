"""GitHub OAuth server example for FastMCP with mounting.

This example demonstrates how to protect a FastMCP server with GitHub OAuth
and mount it under a path prefix in a parent ASGI application.

Required environment variables:
- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID: Your GitHub OAuth app client ID
- FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET: Your GitHub OAuth app client secret

To run:
    python server.py
"""

import os

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider

auth = GitHubProvider(
    client_id=os.getenv("FASTMCP_SERVER_AUTH_GITHUB_CLIENT_ID") or "",
    client_secret=os.getenv("FASTMCP_SERVER_AUTH_GITHUB_CLIENT_SECRET") or "",
    base_url="http://localhost:8000/api",  # Where OAuth endpoints will be accessible
    issuer_url="http://localhost:8000",  # Where auth server metadata is located (root level)
    # redirect_path="/auth/callback",  # Default path - change if using a different callback URL
)

mcp = FastMCP("GitHub OAuth Example Server", auth=auth)


@mcp.tool
def echo(message: str) -> str:
    """Echo the provided message."""
    return message


if __name__ == "__main__":
    # Create the MCP app with internal path only
    mcp_app = mcp.http_app(path="/mcp")

    # Get well-known routes (mounted at root level for RFC compliance)
    # Pass the internal MCP path - it combines with base_url internally
    well_known_routes = auth.get_routes(mcp_path="/mcp")

    # Create parent app and mount everything
    app = Starlette(
        routes=[
            *well_known_routes,  # Well-known discovery routes at root level
            Mount("/api", app=mcp_app),  # MCP app mounted under /api prefix
        ],
        lifespan=mcp_app.lifespan,
    )

    # URLs after mounting:
    # - MCP endpoint: http://localhost:8000/api/mcp
    # - OAuth callback: http://localhost:8000/api/auth/callback
    # - Auth server metadata: http://localhost:8000/.well-known/oauth-authorization-server
    # - Protected resource metadata: http://localhost:8000/.well-known/oauth-protected-resource/api/mcp
    uvicorn.run(app, host="127.0.0.1", port=8000)
