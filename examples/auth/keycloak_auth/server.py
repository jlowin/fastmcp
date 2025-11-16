"""Keycloak OAuth server example for FastMCP.

This example demonstrates how to protect a FastMCP server with Keycloak.

Required environment variables:
- FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL: Your Keycloak realm URL
- FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL: Your FastMCP server base URL

Optional environment variables:
- FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES: Required OAuth scopes (default: "openid,profile")
- FASTMCP_SERVER_AUTH_KEYCLOAK_AUDIENCE: Audience for JWT validation (default: None for development)

To run:
    python server.py
"""

import os

from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.logging import configure_logging

# Load environment overrides before configuring logging
load_dotenv(".env", override=True)

# Configure FastMCP logging to INFO
configure_logging(level="INFO")

realm_url = os.getenv(
    "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL", "http://localhost:8080/realms/fastmcp"
)
base_url = os.getenv("FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL", "http://localhost:8000")
required_scopes = os.getenv(
    "FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES", "openid,profile"
)
# Note: Audience validation is disabled by default for this development example.
# For production, configure Keycloak audience mappers and set FASTMCP_SERVER_AUTH_KEYCLOAK_AUDIENCE
audience = os.getenv("FASTMCP_SERVER_AUTH_KEYCLOAK_AUDIENCE")

auth = KeycloakAuthProvider(
    realm_url=realm_url,
    base_url=base_url,
    required_scopes=required_scopes,
    audience=audience,  # None by default for development
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
    if token is None or token.claims is None:
        raise RuntimeError("No valid access token found. Authentication required.")

    return {
        "sub": token.claims.get("sub"),
        "name": token.claims.get("name"),
        "given_name": token.claims.get("given_name"),
        "family_name": token.claims.get("family_name"),
        "preferred_username": token.claims.get("preferred_username"),
        "scope": token.claims.get("scope"),
    }


if __name__ == "__main__":
    try:
        mcp.run(transport="http", port=8000)
    except KeyboardInterrupt:
        # Graceful shutdown, suppress noisy logs resulting from asyncio.run task cancellation propagation
        pass
    except Exception as e:
        # Unexpected internal error
        print(f"❌ Internal error: {e}")
