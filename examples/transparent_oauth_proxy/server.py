"""Example FastMCP server that uses TransparentOAuthProxyProvider.

1.  Copy `.env.example` to `.env` and fill in the upstream values for your
    Authorization Server.
2.  Load the environment variables (e.g. `source .env`) or rely on a tool such
    as `dotenv` to auto-load them.
3.  Run the server:  
    ```bash
    uvicorn examples.transparent_oauth_proxy.server:app --reload --port 8000
    ```

Navigate to `http://localhost:8000/mcp` (or whichever transport you enable) and
connect with an MCP-compatible client such as Cursor.
"""

from __future__ import annotations

"""Transparent OAuth Proxy Example.

This example automatically loads environment variables from a `.env` file (if
present) using *python-dotenv*.  Place the file either in the project root **or**
alongside this script (`examples/transparent_oauth_proxy/.env`).  The file
should contain the five required upstream settings in simple `KEY=value`
format.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth.providers.transparent_proxy import (
    TransparentOAuthProxyProvider,
)
import logging

# ---------------------------------------------------------------------------
# Load the `.env` file (if present).
# ---------------------------------------------------------------------------

# First look for a .env next to this script; then fall back to the project root.
_THIS_DIR = Path(__file__).resolve().parent
load_dotenv(_THIS_DIR / ".env", override=False)
# Also attempt to load a project-root .env so either location works.
load_dotenv(override=False)

# ---------------------------------------------------------------------------
# Read configuration from environment variables.  In a real deployment you
# would manage these secrets via your orchestrator (Kubernetes, Docker secrets,
# etc.).  For demonstration purposes we simply pull from environment variables.
# ---------------------------------------------------------------------------

REQUIRED_VARS = [
    "UPSTREAM_AUTHORIZATION_ENDPOINT",
    "UPSTREAM_TOKEN_ENDPOINT",
    "UPSTREAM_JWKS_URI",
    "UPSTREAM_CLIENT_ID",
    "UPSTREAM_CLIENT_SECRET",
]

missing = [v for v in REQUIRED_VARS if v not in os.environ]
if missing:
    raise RuntimeError(
        "Missing required environment variables: " + ", ".join(missing)
    )

provider = TransparentOAuthProxyProvider(
    upstream_authorization_endpoint=os.environ["UPSTREAM_AUTHORIZATION_ENDPOINT"],
    upstream_token_endpoint=os.environ["UPSTREAM_TOKEN_ENDPOINT"],
    upstream_jwks_uri=os.environ["UPSTREAM_JWKS_URI"],
    upstream_client_id=os.environ["UPSTREAM_CLIENT_ID"],
    upstream_client_secret=os.environ["UPSTREAM_CLIENT_SECRET"],
    issuer_url="http://localhost:8000",  # Public URL of this FastMCP instance
)

mcp = FastMCP("Transparent-Proxy-Demo", auth=provider)

# Create module-level logger
logger = logging.getLogger("transparent_oauth_proxy")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

@mcp.tool
def add(a: int, b: int) -> int:  # noqa: D401
    """Simple demo tool that requires authentication."""

    return a + b


app = mcp.http_app(path="/mcp")

# ---------------------------------------------------------------------------
# Built-in OAuth routes
# ---------------------------------------------------------------------------
# TransparentOAuthProxyProvider implements all required OAuth server methods,
# so we can rely on FastMCP's standard `create_auth_routes` integration.  No
# additional proxy routes are needed.

# ---------------------------------------------------------------------------
# Additional demo tool: User Info
# ---------------------------------------------------------------------------

@mcp.tool(name="user_info", description="Return information about the currently authenticated OAuth client")
async def user_info() -> dict[str, str]:  # noqa: D401
    """Return the `client_id` embedded in the bearer token used for this request."""

    from fastmcp.server.dependencies import (
        get_access_token as _get_access_token,
        get_context as _get_context,
    )

    # Retrieve context and token dynamically to avoid circular import at module load time.
    try:
        ctx = _get_context()
        access_token = _get_access_token()
    except RuntimeError:
        raise ValueError("Unauthorized: missing bearer token") from None

    import base64, json  # noqa: WPS433

    token_str = access_token.token  # type: ignore[attr-defined]
    # Manually decode JWT payload without verifying signature to avoid external deps
    parts = token_str.split(".")
    if len(parts) < 2:
        raise ValueError("Malformed JWT token")

    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
        claims = json.loads(payload_json)
    except Exception:
        claims = {}

    user_id = str(claims.get("userid") or claims.get("sub") or "unknown")
    client_id = str(claims.get("client_id") or "unknown")

    await ctx.info("Retrieved user info from token claims")

    return {"userid": user_id, "client_id": client_id}