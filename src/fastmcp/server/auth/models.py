from typing import Any

from mcp.server.auth.provider import AccessToken


class AccessTokenWithClaims(AccessToken):
    """AccessToken that includes all JWT claims."""

    claims: dict[str, Any] = {}
