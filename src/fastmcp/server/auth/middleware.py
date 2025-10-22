"""Enhanced authentication middleware with better error messages.

This module provides enhanced versions of MCP SDK authentication middleware
that return more helpful error messages for developers troubleshooting
authentication issues.
"""

from __future__ import annotations

import json

from mcp.server.auth.middleware.bearer_auth import (
    RequireAuthMiddleware as SDKRequireAuthMiddleware,
)
from starlette.types import Send

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class RequireAuthMiddleware(SDKRequireAuthMiddleware):
    """Enhanced authentication middleware with detailed error messages.

    Extends the SDK's RequireAuthMiddleware to provide more actionable
    error messages when authentication fails. This helps developers
    understand what went wrong and how to fix it.
    """

    async def _send_auth_error(
        self, send: Send, status_code: int, error: str, description: str
    ) -> None:
        """Send an authentication error response with enhanced error messages.

        Overrides the SDK's _send_auth_error to provide more detailed
        error descriptions that help developers troubleshoot authentication
        issues.

        Args:
            send: ASGI send callable
            status_code: HTTP status code (401 or 403)
            error: OAuth error code
            description: Base error description
        """
        # Enhance error descriptions based on error type
        enhanced_description = description

        if error == "invalid_token" and status_code == 401:
            # This is the "Authentication required" error
            enhanced_description = (
                "Authentication failed. The provided bearer token is invalid, expired, or no longer recognized by the server. "
                "Common causes: (1) Server restarted and lost ephemeral client registrations, making existing tokens invalid, "
                "(2) Token has expired, (3) Token was revoked. "
                "To resolve: Re-authenticate by initiating a new OAuth flow. If you're seeing this repeatedly, "
                "check that your MCP client supports automatic re-registration when it receives a 400 error "
                "from the /authorize endpoint, or try clearing cached authentication tokens manually."
            )
        elif error == "insufficient_scope":
            # Scope error - already has good detail from SDK
            pass

        # Build WWW-Authenticate header value
        www_auth_parts = [
            f'error="{error}"',
            f'error_description="{enhanced_description}"',
        ]
        if self.resource_metadata_url:
            www_auth_parts.append(f'resource_metadata="{self.resource_metadata_url}"')

        www_authenticate = f"Bearer {', '.join(www_auth_parts)}"

        # Send response
        body = {"error": error, "error_description": enhanced_description}
        body_bytes = json.dumps(body).encode()

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body_bytes)).encode()),
                    (b"www-authenticate", www_authenticate.encode()),
                ],
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
            }
        )

        logger.info(
            "Enhanced auth error response: %s (status=%d)",
            error,
            status_code,
        )
