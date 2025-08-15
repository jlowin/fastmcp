"""GitHub OAuth provider for FastMCP.

This module provides a complete GitHub OAuth integration that's ready to use
with just a client ID and client secret. It handles all the complexity of
GitHub's OAuth flow, token validation, and user management.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.auth.providers.github import GitHubProvider
    
    # Simple GitHub OAuth protection
    auth = GitHubProvider(
        client_id="your-github-client-id",
        client_secret="your-github-client-secret"
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
from fastmcp.server.auth.proxy import OAuthProxy
from fastmcp.server.auth.registry import register_provider
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class GitHubTokenVerifier(TokenVerifier):
    """Token verifier for GitHub OAuth tokens.
    
    GitHub OAuth tokens are opaque (not JWTs), so we verify them
    by calling GitHub's API to check if they're valid and get user info.
    """
    
    def __init__(
        self,
        *,
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
    ):
        """Initialize the GitHub token verifier.
        
        Args:
            required_scopes: Required OAuth scopes (e.g., ['user:email'])
            timeout_seconds: HTTP request timeout
        """
        super().__init__(required_scopes=required_scopes)
        self.timeout_seconds = timeout_seconds
        
    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify GitHub OAuth token by calling GitHub API."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Get token info from GitHub API
                response = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "FastMCP-GitHub-OAuth",
                    }
                )
                
                if response.status_code != 200:
                    logger.debug(
                        "GitHub token verification failed: %d - %s",
                        response.status_code,
                        response.text[:200]
                    )
                    return None
                
                user_data = response.json()
                
                # Get token scopes from GitHub API  
                # GitHub includes scopes in the X-OAuth-Scopes header
                scopes_response = await client.get(
                    "https://api.github.com/user/repos",  # Any authenticated endpoint
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3+json", 
                        "User-Agent": "FastMCP-GitHub-OAuth",
                    }
                )
                
                # Extract scopes from X-OAuth-Scopes header if available
                oauth_scopes_header = scopes_response.headers.get("x-oauth-scopes", "")
                token_scopes = [scope.strip() for scope in oauth_scopes_header.split(",") if scope.strip()]
                
                # If no scopes in header, assume basic scopes based on successful user API call
                if not token_scopes:
                    token_scopes = ["user"]  # Basic scope if we can access user info
                
                # Check required scopes
                if self.required_scopes:
                    token_scopes_set = set(token_scopes)
                    required_scopes_set = set(self.required_scopes)
                    if not required_scopes_set.issubset(token_scopes_set):
                        logger.debug(
                            "GitHub token missing required scopes. Has: %s, Required: %s",
                            token_scopes_set,
                            required_scopes_set,
                        )
                        return None
                
                # Create AccessToken with GitHub user info
                return AccessToken(
                    token=token,
                    client_id=str(user_data.get("id", "unknown")),  # Use GitHub user ID
                    scopes=token_scopes,
                    expires_at=None,  # GitHub tokens don't typically expire
                    claims={
                        "sub": str(user_data["id"]),
                        "login": user_data.get("login"),
                        "name": user_data.get("name"),
                        "email": user_data.get("email"),
                        "avatar_url": user_data.get("avatar_url"),
                        "github_user_data": user_data,
                    }
                )
                
        except httpx.RequestError as e:
            logger.debug("Failed to verify GitHub token: %s", e)
            return None
        except Exception as e:
            logger.debug("GitHub token verification error: %s", e)
            return None


@register_provider("GitHub")
class GitHubProvider(OAuthProxy):
    """Complete GitHub OAuth provider for FastMCP.
    
    This provider makes it trivial to add GitHub OAuth protection to any
    FastMCP server. Just provide your GitHub OAuth app credentials and
    a base URL, and you're ready to go.
    
    Features:
    - Transparent OAuth proxy to GitHub
    - Automatic token validation via GitHub API
    - User information extraction
    - Minimal configuration required
    
    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.github import GitHubProvider
        
        auth = GitHubProvider(
            client_id="Ov23li...",
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
        redirect_path: str = "/oauth/callback",
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
    ):
        """Initialize GitHub OAuth provider.
        
        Args:
            client_id: GitHub OAuth app client ID (e.g., "Ov23li...")
            client_secret: GitHub OAuth app client secret
            base_url: Public URL of your FastMCP server (for OAuth callbacks)
            redirect_path: Redirect path configured in GitHub OAuth app (defaults to "/oauth/callback")
            required_scopes: Required GitHub scopes (defaults to ["user"])
            timeout_seconds: HTTP request timeout for GitHub API calls
        """
        # Default to basic user scope if none specified
        if required_scopes is None:
            required_scopes = ["user"]
        
        # Create GitHub token verifier
        token_verifier = GitHubTokenVerifier(
            required_scopes=required_scopes,
            timeout_seconds=timeout_seconds,
        )
        
        # Initialize OAuth proxy with GitHub endpoints
        super().__init__(
            upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
            upstream_token_endpoint="https://github.com/login/oauth/access_token",
            upstream_client_id=client_id,
            upstream_client_secret=client_secret,
            token_verifier=token_verifier,
            base_url=base_url,
            redirect_path=redirect_path,
            issuer_url=base_url,  # We act as the issuer for client registration
        )
        
        logger.info(
            "Initialized GitHub OAuth provider for client %s with scopes: %s",
            client_id,
            required_scopes,
        )