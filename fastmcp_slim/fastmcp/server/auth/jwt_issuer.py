"""JWT token issuance and verification for FastMCP OAuth Proxy.

This module implements the token factory pattern for OAuth proxies, where the proxy
issues its own JWT tokens to clients instead of forwarding upstream provider tokens.
This maintains proper OAuth 2.0 token audience boundaries.
"""

from __future__ import annotations

import base64
import time
from typing import Any, Literal, overload

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from joserfc import jwk, jwt
from joserfc.errors import JoseError

import fastmcp
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

KDF_ITERATIONS = 1_000_000
KDF_ITERATIONS_TEST = 10

JWTSigningAlgorithm = Literal["HS256", "RS256", "ES256"]

__all__ = [
    "JWTIssuer",
    "JWTSigningAlgorithm",
    "derive_jwt_key",
]


@overload
def derive_jwt_key(*, high_entropy_material: str, salt: str) -> bytes:
    """Derive JWT signing key from a high-entropy key material and server salt."""


@overload
def derive_jwt_key(*, low_entropy_material: str, salt: str) -> bytes:
    """Derive JWT signing key from a low-entropy key material and server salt."""


def derive_jwt_key(
    *,
    high_entropy_material: str | None = None,
    low_entropy_material: str | None = None,
    salt: str,
) -> bytes:
    """Derive JWT signing key from a high-entropy or low-entropy key material and server salt."""
    if high_entropy_material is not None and low_entropy_material is not None:
        raise ValueError(
            "Either high_entropy_material or low_entropy_material must be provided, but not both"
        )

    if high_entropy_material is not None:
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            info=b"Fernet",
        ).derive(key_material=high_entropy_material.encode())

        return base64.urlsafe_b64encode(derived_key)

    if low_entropy_material is not None:
        iterations = (
            KDF_ITERATIONS_TEST if fastmcp.settings.test_mode else KDF_ITERATIONS
        )
        pbkdf2 = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=iterations,
        ).derive(key_material=low_entropy_material.encode())

        return base64.urlsafe_b64encode(pbkdf2)

    raise ValueError(
        "Either high_entropy_material or low_entropy_material must be provided"
    )


class JWTIssuer:
    """Issues and validates FastMCP-signed JWT tokens.

    This issuer creates JWT tokens for MCP clients with proper audience claims,
    maintaining OAuth 2.0 token boundaries. Supports HS256 (symmetric) for
    single-process deployments and RS256 / ES256 (asymmetric) for split-process
    deployments where resource servers verify tokens via JWKS without holding
    the minting key.
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        signing_key: bytes | str,
        algorithm: JWTSigningAlgorithm = "HS256",
        kid: str | None = None,
    ) -> None:
        """Initialize JWT issuer.

        Args:
            issuer: Token issuer (FastMCP server base URL)
            audience: Token audience (typically {base_url}/mcp)
            signing_key: For HS256, a symmetric key (32 bytes). For RS256 or
                ES256, a PEM-encoded private key (bytes or string).
            algorithm: Signing algorithm ("HS256", "RS256", or "ES256").
            kid: Optional explicit key ID. When omitted, asymmetric keys use
                their JWK thumbprint (RFC 7638) as the key ID. HS256 does not
                require a key ID because tokens are verified in-process with
                the same shared secret.
        """
        self.issuer = issuer
        self.audience = audience
        self._signing_key = (
            signing_key.encode() if isinstance(signing_key, str) else signing_key
        )
        self._algorithm: JWTSigningAlgorithm = algorithm

        if algorithm == "HS256":
            self._jwt_key = jwk.import_key(self._signing_key, "oct")
        elif algorithm == "RS256":
            self._jwt_key = jwk.import_key(self._signing_key, "RSA")
        elif algorithm == "ES256":
            self._jwt_key = jwk.import_key(self._signing_key, "EC")
        else:
            raise ValueError(f"Unsupported signing algorithm: {algorithm}")

        if kid is not None:
            self._kid: str | None = kid
        elif algorithm != "HS256":
            self._jwt_key.ensure_kid()
            self._kid = self._jwt_key.kid
        else:
            self._kid = None

    @property
    def algorithm(self) -> JWTSigningAlgorithm:
        """The signing algorithm used by this issuer."""
        return self._algorithm

    @property
    def kid(self) -> str | None:
        """The key ID included in JWT headers (None for HS256)."""
        return self._kid

    @property
    def is_asymmetric(self) -> bool:
        """Whether this issuer uses asymmetric signing."""
        return self._algorithm in ("RS256", "ES256")

    def public_jwks(self) -> dict[str, Any]:
        """Return the public JSON Web Key Set for this issuer.

        Only meaningful for asymmetric algorithms (RS256 / ES256). The returned
        set contains public key material only — never the private signing key.

        Returns:
            A dict with a ``keys`` list of JWK objects suitable for serializing
            as the body of a ``GET /.well-known/jwks.json`` response.

        Raises:
            ValueError: If called on an HS256 issuer (no JWKS exists).
        """
        if not self.is_asymmetric:
            raise ValueError(
                "public_jwks() is only available for asymmetric algorithms "
                "(RS256 or ES256). HS256 uses a shared secret and has no JWKS."
            )
        return {"keys": [self._jwt_key.as_dict(private=False)]}

    def issue_access_token(
        self,
        client_id: str,
        scopes: list[str],
        jti: str,
        expires_in: int = 3600,
        upstream_claims: dict[str, Any] | None = None,
        subject: str | None = None,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """Issue a minimal FastMCP access token.

        FastMCP tokens are reference tokens containing only the minimal claims
        needed for validation and lookup. The JTI maps to the upstream token
        which contains actual user identity and authorization data.

        Args:
            client_id: MCP client ID
            scopes: Token scopes
            jti: Unique token identifier (maps to upstream token)
            expires_in: Token lifetime in seconds
            upstream_claims: Optional claims from upstream IdP token to include
            subject: Optional `sub` claim. Set for self-contained tokens (e.g.
                minted from an ID-JAG) where the subject is carried directly in
                the token rather than looked up via a JTI mapping.
            extra_claims: Optional additional top-level claims to embed. Used to
                mark self-contained tokens (e.g. the ID-JAG issuer/marker) so
                `load_access_token` can validate them without a JTI mapping.

        Returns:
            Signed JWT token
        """
        now = int(time.time())

        header = self._build_header()
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "client_id": client_id,
            "scope": " ".join(scopes),
            "exp": now + expires_in,
            "iat": now,
            "jti": jti,
        }

        if subject is not None:
            payload["sub"] = subject

        if extra_claims:
            payload.update(extra_claims)

        if upstream_claims:
            payload["upstream_claims"] = upstream_claims

        token = jwt.encode(
            header,
            payload,
            self._jwt_key,
            algorithms=[self._algorithm],
        )

        logger.debug(
            "Issued access token for client=%s jti=%s exp=%d",
            client_id,
            jti[:8],
            payload["exp"],
        )

        return token

    def issue_refresh_token(
        self,
        client_id: str,
        scopes: list[str],
        jti: str,
        expires_in: int,
        upstream_claims: dict[str, Any] | None = None,
    ) -> str:
        """Issue a minimal FastMCP refresh token.

        FastMCP refresh tokens are reference tokens containing only the minimal
        claims needed for validation and lookup. The JTI maps to the upstream
        token which contains actual user identity and authorization data.

        Args:
            client_id: MCP client ID
            scopes: Token scopes
            jti: Unique token identifier (maps to upstream token)
            expires_in: Token lifetime in seconds (should match upstream refresh expiry)
            upstream_claims: Optional claims from upstream IdP token to include

        Returns:
            Signed JWT token
        """
        now = int(time.time())

        header = self._build_header()
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "client_id": client_id,
            "scope": " ".join(scopes),
            "exp": now + expires_in,
            "iat": now,
            "jti": jti,
            "token_use": "refresh",
        }

        if upstream_claims:
            payload["upstream_claims"] = upstream_claims

        token = jwt.encode(
            header,
            payload,
            self._jwt_key,
            algorithms=[self._algorithm],
        )

        logger.debug(
            "Issued refresh token for client=%s jti=%s exp=%d",
            client_id,
            jti[:8],
            payload["exp"],
        )

        return token

    def verify_token(
        self,
        token: str,
        expected_token_use: str = "access",
    ) -> dict[str, Any]:
        """Verify and decode a FastMCP token.

        Validates JWT signature, expiration, issuer, audience, and token type.

        Args:
            token: JWT token to verify
            expected_token_use: Expected token type ("access" or "refresh").
                Defaults to "access", which rejects refresh tokens.

        Returns:
            Decoded token payload

        Raises:
            JoseError: If token is invalid, expired, or has wrong claims
        """
        try:
            # Decode and verify signature
            payload = jwt.decode(
                token,
                self._jwt_key,
                algorithms=[self._algorithm],
            ).claims

            # Validate token type
            token_use = payload.get("token_use", "access")
            if token_use != expected_token_use:
                logger.debug(
                    "Token type mismatch: expected %s, got %s",
                    expected_token_use,
                    token_use,
                )
                raise JoseError(
                    f"Token type mismatch: expected {expected_token_use}, "
                    f"got {token_use}"
                )

            # Validate expiration
            exp = payload.get("exp")
            if exp is not None and exp < time.time():
                logger.debug("Token expired")
                raise JoseError("Token has expired")

            # Validate issuer
            if payload.get("iss") != self.issuer:
                logger.debug("Token has invalid issuer")
                raise JoseError("Invalid token issuer")

            # Validate audience
            if payload.get("aud") != self.audience:
                logger.debug("Token has invalid audience")
                raise JoseError("Invalid token audience")

            logger.debug(
                "Token verified successfully for subject=%s", payload.get("sub")
            )
            return payload

        except JoseError as e:
            logger.debug("Token validation failed: %s", e)
            raise

    def _build_header(self) -> dict[str, Any]:
        """Build the JWT header for this issuer's algorithm."""
        header: dict[str, Any] = {"alg": self._algorithm, "typ": "JWT"}
        if self._kid is not None:
            header["kid"] = self._kid
        return header
