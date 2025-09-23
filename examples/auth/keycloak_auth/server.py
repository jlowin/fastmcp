"""Keycloak OAuth server example for FastMCP.

This example demonstrates how to protect a FastMCP server with Keycloak.

Required environment variables:
- FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL: Your Keycloak realm URL
- FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL: Your FastMCP server base URL

To run:
    python server.py
"""

import logging
import os

from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider
from fastmcp.server.dependencies import get_access_token

logging.basicConfig(level=logging.DEBUG)

load_dotenv(".env", override=True)

auth = KeycloakAuthProvider(
    realm_url=os.getenv("FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL")
    or "http://localhost:8080/realms/fastmcp",
    base_url=os.getenv("FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL")
    or "http://localhost:8000",
    required_scopes=["openid", "profile"],
)

mcp = FastMCP("Keycloak OAuth Example Server", auth=auth)


@mcp.tool
def echo(message: str) -> str:
    """Echo the provided message."""
    return message


@mcp.tool
async def get_access_token_claims() -> dict:
    """Get the authenticated user's access token claims."""
    token = get_access_token()
    return {
        "sub": token.claims.get("sub"),
        "preferred_username": token.claims.get("preferred_username"),
        "email": token.claims.get("email"),
        "realm_access": token.claims.get("realm_access", {}),
        "resource_access": token.claims.get("resource_access", {}),
    }


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
