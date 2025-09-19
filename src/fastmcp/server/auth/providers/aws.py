"""AWS Cognito OAuth provider for FastMCP.

This module provides a complete AWS Cognito OAuth integration that's ready to use
with a user pool ID, domain prefix, client ID and client secret. It handles all
the complexity of AWS Cognito's OAuth flow, token validation, and user management.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.auth.providers.aws_cognito import AWSCognitoProvider

    # Simple AWS Cognito OAuth protection
    auth = AWSCognitoProvider(
        user_pool_id="your-user-pool-id",
        aws_region="eu-central-1",
        domain_prefix="your-domain-prefix",
        client_id="your-cognito-client-id",
        client_secret="your-cognito-client-secret"
    )

    mcp = FastMCP("My Protected Server", auth=auth)
    ```
"""

from __future__ import annotations

import time

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError
from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastmcp.server.auth import TokenVerifier
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.utilities.auth import parse_scopes
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.types import NotSet, NotSetT

logger = get_logger(__name__)


class AWSCognitoProviderSettings(BaseSettings):
    """Settings for AWS Cognito OAuth provider."""

    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_SERVER_AUTH_AWS_COGNITO_",
        env_file=".env",
        extra="ignore",
    )

    user_pool_id: str | None = None
    aws_region: str | None = None
    domain_prefix: str | None = None
    client_id: str | None = None
    client_secret: SecretStr | None = None
    base_url: AnyHttpUrl | str | None = None
    redirect_path: str | None = None
    required_scopes: list[str] | None = None
    timeout_seconds: int | None = None
    allowed_client_redirect_uris: list[str] | None = None

    @field_validator("required_scopes", mode="before")
    @classmethod
    def _parse_scopes(cls, v):
        return parse_scopes(v)


class AWSCognitoTokenVerifier(TokenVerifier):
    """Token verifier for AWS Cognito JWT tokens.

    AWS Cognito OAuth tokens are JWTs, so we verify them
    by validating the JWT signature against Cognito's public keys
    and extracting user info from the token claims.
    """

    def __init__(
        self,
        *,
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
        user_pool_id: str,
        aws_region: str = "eu-central-1",
    ):
        """Initialize the AWS Cognito token verifier.

        Args:
            required_scopes: Required OAuth scopes (e.g., ['openid', 'email'])
            timeout_seconds: HTTP request timeout
            user_pool_id: AWS Cognito User Pool ID
            aws_region: AWS region where the User Pool is located
        """
        super().__init__(required_scopes=required_scopes)
        self.timeout_seconds = timeout_seconds
        self.user_pool_id = user_pool_id
        self.aws_region = aws_region
        self.issuer = f"https://cognito-idp.{aws_region}.amazonaws.com/{user_pool_id}"
        self.jwks_uri = f"{self.issuer}/.well-known/jwks.json"
        self.jwt = JsonWebToken(["RS256"])
        self._jwks_cache: dict[str, str] = {}
        self._jwks_cache_time: float = 0
        self._cache_ttl = 3600  # 1 hour

    async def _get_verification_key(self, token: str) -> str:
        """Get the verification key for the token from JWKS."""
        # Extract kid from token header for JWKS lookup
        try:
            import base64
            import json

            header_b64 = token.split(".")[0]
            header_b64 += "=" * (4 - len(header_b64) % 4)  # Add padding
            header = json.loads(base64.urlsafe_b64decode(header_b64))
            kid = header.get("kid")

            return await self._get_jwks_key(kid)

        except Exception as e:
            raise ValueError(f"Failed to extract key ID from token: {e}")

    async def _get_jwks_key(self, kid: str | None) -> str:
        """Fetch key from JWKS with caching."""
        current_time = time.time()

        # Check cache first
        if current_time - self._jwks_cache_time < self._cache_ttl:
            if kid and kid in self._jwks_cache:
                return self._jwks_cache[kid]
            elif not kid and len(self._jwks_cache) == 1:
                # If no kid but only one key cached, use it
                return next(iter(self._jwks_cache.values()))

        # Fetch JWKS
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.jwks_uri)
                response.raise_for_status()
                jwks_data = response.json()

            # Cache all keys
            self._jwks_cache = {}
            for key_data in jwks_data.get("keys", []):
                key_kid = key_data.get("kid")
                jwk = JsonWebKey.import_key(key_data)
                public_key = jwk.get_public_key()  # type: ignore

                if key_kid:
                    self._jwks_cache[key_kid] = public_key
                else:
                    # Key without kid - use a default identifier
                    self._jwks_cache["_default"] = public_key

            self._jwks_cache_time = current_time

            # Select the appropriate key
            if kid:
                if kid not in self._jwks_cache:
                    logger.debug("JWKS key lookup failed: key ID '%s' not found", kid)
                    raise ValueError(f"Key ID '{kid}' not found in JWKS")
                return self._jwks_cache[kid]
            else:
                # No kid in token - only allow if there's exactly one key
                if len(self._jwks_cache) == 1:
                    return next(iter(self._jwks_cache.values()))
                elif len(self._jwks_cache) > 1:
                    raise ValueError(
                        "Multiple keys in JWKS but no key ID (kid) in token"
                    )
                else:
                    raise ValueError("No keys found in JWKS")

        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch JWKS: {e}")
        except Exception as e:
            logger.debug(f"JWKS fetch failed: {e}")
            raise ValueError(f"Failed to fetch JWKS: {e}")

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify AWS Cognito JWT token."""
        try:
            # Check if token looks like a JWT (should have 3 parts separated by dots)
            if token.count(".") != 2:
                logger.debug(
                    "Token is not a JWT format (expected 3 parts, got %d)",
                    token.count(".") + 1,
                )
                return None

            # Get verification key (from JWKS)
            verification_key = await self._get_verification_key(token)

            # Decode and verify the JWT token
            claims = self.jwt.decode(token, verification_key)

            # Extract client ID early for logging
            client_id = claims.get("client_id") or claims.get("sub") or "unknown"

            # Validate expiration
            exp = claims.get("exp")
            if exp and exp < time.time():
                logger.debug(
                    "Token validation failed: expired token for client %s", client_id
                )
                return None

            # Validate issuer
            if claims.get("iss") != self.issuer:
                logger.debug(
                    "Token validation failed: issuer mismatch for client %s",
                    client_id,
                )
                return None

            # Extract scopes from token
            token_scopes = []
            if "scope" in claims:
                if isinstance(claims["scope"], str):
                    token_scopes = claims["scope"].split()
                elif isinstance(claims["scope"], list):
                    token_scopes = claims["scope"]

            # Check required scopes
            if self.required_scopes:
                token_scopes_set = set(token_scopes)
                required_scopes_set = set(self.required_scopes)
                if not required_scopes_set.issubset(token_scopes_set):
                    logger.debug(
                        "Cognito token missing required scopes. Has %s, needs %s",
                        token_scopes_set,
                        required_scopes_set,
                    )
                    return None

            # Create AccessToken with Cognito user info
            return AccessToken(
                token=token,
                client_id=str(client_id),
                scopes=token_scopes,
                expires_at=int(exp) if exp else None,
                claims={
                    "sub": claims.get("sub"),
                    "username": claims.get("username"),
                    "email": claims.get("email"),
                    "email_verified": claims.get("email_verified"),
                    "name": claims.get("name"),
                    "given_name": claims.get("given_name"),
                    "family_name": claims.get("family_name"),
                    "cognito_groups": claims.get("cognito:groups", []),
                    "cognito_user_data": claims,
                },
            )

        except JoseError:
            logger.debug("Token validation failed: JWT signature/format invalid")
            return None
        except Exception as e:
            logger.debug("Cognito token verification error: %s", e)
            return None


class AWSCognitoProvider(OAuthProxy):
    """Complete AWS Cognito OAuth provider for FastMCP.

    This provider makes it trivial to add AWS Cognito OAuth protection to any
    FastMCP server. Just provide your Cognito app credentials and
    a base URL, and you're ready to go.

    Features:
    - Transparent OAuth proxy to AWS Cognito
    - Automatic JWT token validation via Cognito's public keys
    - User information extraction from JWT claims
    - Support for Cognito User Pools

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.aws_cognito import AWSCognitoProvider

        auth = AWSCognitoProvider(
            user_pool_id="eu-central-1_XXXXXXXXX",
            aws_region="eu-central-1",
            domain_prefix="your-domain-prefix",
            client_id="your-cognito-client-id",
            client_secret="your-cognito-client-secret",
            base_url="https://my-server.com"
        )

        mcp = FastMCP("My App", auth=auth)
        ```
    """

    def __init__(
        self,
        *,
        user_pool_id: str | NotSetT = NotSet,
        aws_region: str | NotSetT = NotSet,
        domain_prefix: str | NotSetT = NotSet,
        client_id: str | NotSetT = NotSet,
        client_secret: str | NotSetT = NotSet,
        base_url: AnyHttpUrl | str | NotSetT = NotSet,
        redirect_path: str | NotSetT = NotSet,
        required_scopes: list[str] | NotSetT = NotSet,
        timeout_seconds: int | NotSetT = NotSet,
        allowed_client_redirect_uris: list[str] | NotSetT = NotSet,
    ):
        """Initialize AWS Cognito OAuth provider.

        Args:
            user_pool_id: Your Cognito User Pool ID (e.g., "eu-central-1_XXXXXXXXX")
            aws_region: AWS region where your User Pool is located (defaults to "eu-central-1")
            domain_prefix: Your Cognito domain prefix (e.g., "your-domain" - will become "your-domain.auth.{region}.amazoncognito.com")
            client_id: Cognito app client ID
            client_secret: Cognito app client secret
            base_url: Public URL of your FastMCP server (for OAuth callbacks)
            redirect_path: Redirect path configured in Cognito app (defaults to "/auth/callback")
            required_scopes: Required Cognito scopes (defaults to ["openid"])
            timeout_seconds: HTTP request timeout for Cognito API calls
            allowed_client_redirect_uris: List of allowed redirect URI patterns for MCP clients.
                If None (default), all URIs are allowed. If empty list, no URIs are allowed.
        """

        settings = AWSCognitoProviderSettings.model_validate(
            {
                k: v
                for k, v in {
                    "user_pool_id": user_pool_id,
                    "aws_region": aws_region,
                    "domain_prefix": domain_prefix,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "base_url": base_url,
                    "redirect_path": redirect_path,
                    "required_scopes": required_scopes,
                    "timeout_seconds": timeout_seconds,
                    "allowed_client_redirect_uris": allowed_client_redirect_uris,
                }.items()
                if v is not NotSet
            }
        )

        # Validate required settings
        if not settings.user_pool_id:
            raise ValueError(
                "user_pool_id is required - set via parameter or FASTMCP_SERVER_AUTH_AWS_COGNITO_USER_POOL_ID"
            )
        if not settings.domain_prefix:
            raise ValueError(
                "domain_prefix is required - set via parameter or FASTMCP_SERVER_AUTH_AWS_COGNITO_DOMAIN_PREFIX"
            )
        if not settings.client_id:
            raise ValueError(
                "client_id is required - set via parameter or FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_ID"
            )
        if not settings.client_secret:
            raise ValueError(
                "client_secret is required - set via parameter or FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_SECRET"
            )

        # Apply defaults
        timeout_seconds_final = settings.timeout_seconds or 10
        required_scopes_final = settings.required_scopes or ["openid"]
        allowed_client_redirect_uris_final = settings.allowed_client_redirect_uris
        aws_region_final = settings.aws_region or "eu-central-1"
        redirect_path_final = settings.redirect_path or "/auth/callback"

        # Construct full cognito domain from prefix and region
        cognito_domain = (
            f"{settings.domain_prefix}.auth.{aws_region_final}.amazoncognito.com"
        )

        # Create Cognito token verifier
        token_verifier = AWSCognitoTokenVerifier(
            required_scopes=required_scopes_final,
            timeout_seconds=timeout_seconds_final,
            user_pool_id=settings.user_pool_id,
            aws_region=aws_region_final,
        )

        # Extract secret string from SecretStr
        client_secret_str = (
            settings.client_secret.get_secret_value() if settings.client_secret else ""
        )

        # Initialize OAuth proxy with Cognito endpoints
        super().__init__(
            upstream_authorization_endpoint=f"https://{cognito_domain}/oauth2/authorize",
            upstream_token_endpoint=f"https://{cognito_domain}/oauth2/token",
            upstream_client_id=settings.client_id,
            upstream_client_secret=client_secret_str,
            token_verifier=token_verifier,
            base_url=settings.base_url,
            redirect_path=redirect_path_final,
            issuer_url=settings.base_url,  # We act as the issuer for client registration
            allowed_client_redirect_uris=allowed_client_redirect_uris_final,
        )

        logger.info(
            "Initialized AWS Cognito OAuth provider for client %s with scopes: %s",
            settings.client_id,
            required_scopes_final,
        )
