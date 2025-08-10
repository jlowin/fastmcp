"""Discord OAuth provider for FastMCP.

This module provides a complete Discord OAuth integration that's ready to use
with just a client ID and client secret. It handles all the complexity of
Discord's OAuth flow, token validation, and user management.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.auth.providers.discord import DiscordProvider
    
    # Simple Discord OAuth protection
    auth = DiscordProvider(
        client_id="your-discord-client-id",
        client_secret="your-discord-client-secret"
    )
    
    mcp = FastMCP("My Protected Server", auth=auth)
    ```
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import AnyHttpUrl

from fastmcp.server.auth import TokenVerifier
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.proxy import OAuthProxy
from fastmcp.server.auth.registry import register_provider
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class DiscordTokenVerifier(TokenVerifier):
    """Token verifier for Discord OAuth tokens.
    
    Discord OAuth tokens are bearer tokens that can be verified
    by calling Discord's user API to check validity and get user info.
    """
    
    def __init__(
        self,
        *,
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
    ):
        """Initialize the Discord token verifier.
        
        Args:
            required_scopes: Required OAuth scopes (e.g., ['identify', 'email'])
            timeout_seconds: HTTP request timeout
        """
        super().__init__(required_scopes=required_scopes)
        self.timeout_seconds = timeout_seconds
        
    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify Discord OAuth token by calling Discord's user API."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Get user info from Discord API to validate token
                response = await client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "FastMCP-Discord-OAuth",
                    }
                )
                
                if response.status_code != 200:
                    logger.debug(
                        "Discord token verification failed: %d - %s",
                        response.status_code,
                        response.text[:200]
                    )
                    return None
                
                user_data = response.json()
                
                # Discord doesn't provide token scope info in the user endpoint
                # We'll assume the token has the scopes we need based on successful API call
                token_scopes = ["identify"]  # Basic scope if we can access user info
                
                # If we need email and the user data includes it, assume email scope
                if user_data.get("email"):
                    token_scopes.append("email")
                
                # Check required scopes (limited verification since Discord doesn't expose this)
                if self.required_scopes:
                    token_scopes_set = set(token_scopes)
                    required_scopes_set = set(self.required_scopes)
                    # Only check for scopes we can detect
                    detectable_required = required_scopes_set.intersection({"identify", "email"})
                    if detectable_required and not detectable_required.issubset(token_scopes_set):
                        logger.debug(
                            "Discord token missing detectable required scopes. Has: %s, Required: %s",
                            token_scopes_set,
                            detectable_required,
                        )
                        return None
                
                # Create AccessToken with Discord user info
                return AccessToken(
                    token=token,
                    client_id=str(user_data.get("id", "unknown")),  # Use Discord user ID
                    scopes=token_scopes,
                    expires_at=None,  # Discord tokens don't typically provide expiration in user endpoint
                    claims={
                        "sub": str(user_data["id"]),
                        "username": user_data.get("username"),
                        "discriminator": user_data.get("discriminator"),
                        "email": user_data.get("email"),
                        "verified": user_data.get("verified"),
                        "avatar": user_data.get("avatar"),
                        "banner": user_data.get("banner"),
                        "accent_color": user_data.get("accent_color"),
                        "locale": user_data.get("locale"),
                        "mfa_enabled": user_data.get("mfa_enabled"),
                        "premium_type": user_data.get("premium_type"),
                        "public_flags": user_data.get("public_flags"),
                        "discord_user_data": user_data,
                    }
                )
                
        except httpx.RequestError as e:
            logger.debug("Failed to verify Discord token: %s", e)
            return None
        except Exception as e:
            logger.debug("Discord token verification error: %s", e)
            return None


@register_provider("Discord")
class DiscordProvider(OAuthProxy):
    """Complete Discord OAuth provider for FastMCP.
    
    This provider makes it trivial to add Discord OAuth protection to any
    FastMCP server. Just provide your Discord OAuth app credentials and
    a base URL, and you're ready to go.
    
    Features:
    - Transparent OAuth proxy to Discord
    - Automatic token validation via Discord's user API
    - User information extraction including Discord-specific data
    - Minimal configuration required
    
    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.discord import DiscordProvider
        
        auth = DiscordProvider(
            client_id="123456789012345678",
            client_secret="abc123...",
            base_url="https://my-server.com"  # Optional, defaults to http://localhost:8000
        )
        
        mcp = FastMCP("My App", auth=auth)
        ```
    """
    
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        base_url: AnyHttpUrl | str = "http://localhost:8000",
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
    ):
        """Initialize Discord OAuth provider.
        
        Args:
            client_id: Discord OAuth client ID (numeric string)
            client_secret: Discord OAuth client secret
            base_url: Public URL of your FastMCP server (for OAuth callbacks)
            required_scopes: Required Discord scopes (defaults to ["identify"])
            timeout_seconds: HTTP request timeout for Discord API calls
        """
        # Default to identify scope if none specified
        if required_scopes is None:
            required_scopes = ["identify"]
        
        # Create Discord token verifier
        token_verifier = DiscordTokenVerifier(
            required_scopes=required_scopes,
            timeout_seconds=timeout_seconds,
        )
        
        # Initialize OAuth proxy with Discord endpoints
        super().__init__(
            upstream_authorization_endpoint="https://discord.com/api/oauth2/authorize",
            upstream_token_endpoint="https://discord.com/api/oauth2/token",
            upstream_client_id=client_id,
            upstream_client_secret=client_secret,
            token_verifier=token_verifier,
            base_url=base_url,
            issuer_url=base_url,  # We act as the issuer for client registration
        )
        
        logger.info(
            "Initialized Discord OAuth provider for client %s with scopes: %s",
            client_id,
            required_scopes,
        )