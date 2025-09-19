"""Unit tests for AWS Cognito OAuth provider."""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from authlib.jose.errors import JoseError

from fastmcp.server.auth.providers.aws import (
    AWSCognitoProvider,
    AWSCognitoProviderSettings,
    AWSCognitoTokenVerifier,
)


class TestAWSCognitoProviderSettings:
    """Test settings for AWS Cognito OAuth provider."""

    def test_settings_from_env_vars(self):
        """Test that settings can be loaded from environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_USER_POOL_ID": "us-east-1_XXXXXXXXX",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_AWS_REGION": "us-east-1",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_DOMAIN_PREFIX": "my-app",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_ID": "env_client_id",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_SECRET": "env_secret",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_BASE_URL": "https://example.com",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_REDIRECT_PATH": "/custom/callback",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_TIMEOUT_SECONDS": "30",
            },
        ):
            settings = AWSCognitoProviderSettings()

            assert settings.user_pool_id == "us-east-1_XXXXXXXXX"
            assert settings.aws_region == "us-east-1"
            assert settings.domain_prefix == "my-app"
            assert settings.client_id == "env_client_id"
            assert (
                settings.client_secret
                and settings.client_secret.get_secret_value() == "env_secret"
            )
            assert settings.base_url == "https://example.com"
            assert settings.redirect_path == "/custom/callback"
            assert settings.timeout_seconds == 30

    def test_settings_explicit_override_env(self):
        """Test that explicit settings override environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_USER_POOL_ID": "env_pool_id",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_ID": "env_client_id",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_SECRET": "env_secret",
            },
        ):
            settings = AWSCognitoProviderSettings.model_validate(
                {
                    "user_pool_id": "explicit_pool_id",
                    "client_id": "explicit_client_id",
                    "client_secret": "explicit_secret",
                }
            )

            assert settings.user_pool_id == "explicit_pool_id"
            assert settings.client_id == "explicit_client_id"
            assert (
                settings.client_secret
                and settings.client_secret.get_secret_value() == "explicit_secret"
            )


class TestAWSCognitoProvider:
    """Test AWSCognitoProvider initialization."""

    def test_init_with_explicit_params(self):
        """Test initialization with explicit parameters."""
        provider = AWSCognitoProvider(
            user_pool_id="us-east-1_XXXXXXXXX",
            aws_region="us-east-1",
            domain_prefix="my-app",
            client_id="test_client",
            client_secret="test_secret",
            base_url="https://example.com",
            redirect_path="/custom/callback",
            required_scopes=["openid", "email"],
            timeout_seconds=30,
        )

        # Check that the provider was initialized correctly
        assert provider._upstream_client_id == "test_client"
        assert provider._upstream_client_secret.get_secret_value() == "test_secret"
        assert (
            str(provider.base_url) == "https://example.com/"
        )  # URLs get normalized with trailing slash
        assert provider._redirect_path == "/custom/callback"
        assert (
            provider._upstream_authorization_endpoint
            == "https://my-app.auth.us-east-1.amazoncognito.com/oauth2/authorize"
        )
        assert (
            provider._upstream_token_endpoint
            == "https://my-app.auth.us-east-1.amazoncognito.com/oauth2/token"
        )

    @pytest.mark.parametrize(
        "scopes_env",
        [
            "openid,email",
            '["openid", "email"]',
        ],
    )
    def test_init_with_env_vars(self, scopes_env):
        """Test initialization with environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_USER_POOL_ID": "us-east-1_XXXXXXXXX",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_AWS_REGION": "us-east-1",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_DOMAIN_PREFIX": "my-app",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_ID": "env_client_id",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_SECRET": "env_secret",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_BASE_URL": "https://env-example.com",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_REQUIRED_SCOPES": scopes_env,
            },
        ):
            provider = AWSCognitoProvider()

            assert provider._upstream_client_id == "env_client_id"
            assert provider._upstream_client_secret.get_secret_value() == "env_secret"
            assert str(provider.base_url) == "https://env-example.com/"
            assert provider._token_validator.required_scopes == ["openid", "email"]

    def test_init_explicit_overrides_env(self):
        """Test that explicit parameters override environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_USER_POOL_ID": "env_pool_id",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_DOMAIN_PREFIX": "env-app",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_ID": "env_client_id",
                "FASTMCP_SERVER_AUTH_AWS_COGNITO_CLIENT_SECRET": "env_secret",
            },
        ):
            provider = AWSCognitoProvider(
                user_pool_id="explicit_pool_id",
                domain_prefix="explicit-app",
                client_id="explicit_client",
                client_secret="explicit_secret",
            )

            assert provider._upstream_client_id == "explicit_client"
            assert (
                provider._upstream_client_secret.get_secret_value() == "explicit_secret"
            )
            assert (
                "explicit-app.auth.eu-central-1.amazoncognito.com"
                in provider._upstream_authorization_endpoint
            )

    def test_init_missing_user_pool_id_raises_error(self):
        """Test that missing user_pool_id raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="user_pool_id is required"):
                AWSCognitoProvider(
                    domain_prefix="my-app",
                    client_id="test_client",
                    client_secret="test_secret",
                )

    def test_init_missing_domain_prefix_raises_error(self):
        """Test that missing domain_prefix raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="domain_prefix is required"):
                AWSCognitoProvider(
                    user_pool_id="us-east-1_XXXXXXXXX",
                    client_id="test_client",
                    client_secret="test_secret",
                )

    def test_init_missing_client_id_raises_error(self):
        """Test that missing client_id raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="client_id is required"):
                AWSCognitoProvider(
                    user_pool_id="us-east-1_XXXXXXXXX",
                    domain_prefix="my-app",
                    client_secret="test_secret",
                )

    def test_init_missing_client_secret_raises_error(self):
        """Test that missing client_secret raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="client_secret is required"):
                AWSCognitoProvider(
                    user_pool_id="us-east-1_XXXXXXXXX",
                    domain_prefix="my-app",
                    client_id="test_client",
                )

    def test_init_defaults(self):
        """Test that default values are applied correctly."""
        provider = AWSCognitoProvider(
            user_pool_id="us-east-1_XXXXXXXXX",
            domain_prefix="my-app",
            client_id="test_client",
            client_secret="test_secret",
        )

        # Check defaults
        assert provider.base_url is None
        assert provider._redirect_path == "/auth/callback"
        assert provider._token_validator.required_scopes == ["openid"]
        assert provider._token_validator.aws_region == "eu-central-1"

    def test_domain_construction(self):
        """Test that Cognito domain is constructed correctly."""
        provider = AWSCognitoProvider(
            user_pool_id="us-west-2_YYYYYYYY",
            aws_region="us-west-2",
            domain_prefix="test-app",
            client_id="test_client",
            client_secret="test_secret",
        )

        assert (
            provider._upstream_authorization_endpoint
            == "https://test-app.auth.us-west-2.amazoncognito.com/oauth2/authorize"
        )
        assert (
            provider._upstream_token_endpoint
            == "https://test-app.auth.us-west-2.amazoncognito.com/oauth2/token"
        )


class TestAWSCognitoTokenVerifier:
    """Test AWSCognitoTokenVerifier."""

    def test_init_with_custom_scopes(self):
        """Test initialization with custom required scopes."""
        verifier = AWSCognitoTokenVerifier(
            required_scopes=["openid", "email"],
            timeout_seconds=30,
            user_pool_id="us-east-1_XXXXXXXXX",
            aws_region="us-east-1",
        )

        assert verifier.required_scopes == ["openid", "email"]
        assert verifier.timeout_seconds == 30
        assert verifier.user_pool_id == "us-east-1_XXXXXXXXX"
        assert verifier.aws_region == "us-east-1"
        assert (
            verifier.issuer
            == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXXXXX"
        )

    def test_init_defaults(self):
        """Test initialization with defaults."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        assert verifier.required_scopes == []
        assert verifier.timeout_seconds == 10
        assert verifier.aws_region == "eu-central-1"

    @pytest.mark.asyncio
    async def test_verify_token_invalid_jwt_format(self):
        """Test token verification with invalid JWT format."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        # Test token with wrong number of parts
        result = await verifier.verify_token("invalid_token")
        assert result is None

        # Test token with only two parts
        result = await verifier.verify_token("header.payload")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_jwks_fetch_failure(self):
        """Test token verification when JWKS fetch fails."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        # Mock httpx.AsyncClient to simulate JWKS fetch failure
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Simulate 404 response from JWKS endpoint
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = Exception("404 Not Found")
            mock_client.get.return_value = mock_response

            # Use a properly formatted JWT token
            valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWV9.signature"

            result = await verifier.verify_token(valid_jwt)
            assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_success(self):
        """Test successful token verification."""
        verifier = AWSCognitoTokenVerifier(
            required_scopes=["openid"],
            user_pool_id="us-east-1_XXXXXXXXX",
            aws_region="us-east-1",
        )

        # Mock current time for token validation
        current_time = time.time()
        future_time = int(current_time + 3600)  # Token expires in 1 hour

        # Mock JWT payload
        mock_payload = {
            "sub": "user-id-123",
            "client_id": "cognito-client-id",
            "username": "testuser",
            "email": "test@example.com",
            "email_verified": True,
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "scope": "openid email",
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXXXXX",
            "exp": future_time,
            "iat": int(current_time),
            "cognito:groups": ["admin", "users"],
        }

        # Mock JWKS response
        mock_jwks = {
            "keys": [
                {
                    "kid": "test-kid",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": "test-modulus",
                    "e": "AQAB",
                }
            ]
        }

        # Mock the verification key
        mock_public_key = "mock-public-key"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock JWKS fetch
            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks
            mock_client.get.return_value = mock_response

            # Mock JWT decoding
            with patch.object(
                verifier, "_get_verification_key", return_value=mock_public_key
            ):
                with patch.object(verifier.jwt, "decode", return_value=mock_payload):
                    valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"

                    result = await verifier.verify_token(valid_jwt)

                    assert result is not None
                    assert result.token == valid_jwt
                    assert result.client_id == "cognito-client-id"
                    assert result.scopes == ["openid", "email"]
                    assert result.expires_at == future_time
                    assert result.claims["sub"] == "user-id-123"
                    assert result.claims["username"] == "testuser"
                    assert result.claims["email"] == "test@example.com"
                    assert result.claims["name"] == "Test User"
                    assert result.claims["cognito_groups"] == ["admin", "users"]

    @pytest.mark.asyncio
    async def test_verify_token_expired(self):
        """Test token verification with expired token."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        # Mock expired JWT payload
        past_time = int(time.time() - 3600)  # Token expired 1 hour ago
        mock_payload = {
            "sub": "user-id-123",
            "exp": past_time,
            "iss": "https://cognito-idp.eu-central-1.amazonaws.com/us-east-1_XXXXXXXXX",
        }

        mock_public_key = "mock-public-key"

        with patch.object(
            verifier, "_get_verification_key", return_value=mock_public_key
        ):
            with patch.object(verifier.jwt, "decode", return_value=mock_payload):
                valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"

                result = await verifier.verify_token(valid_jwt)
                assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_wrong_issuer(self):
        """Test token verification with wrong issuer."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
            aws_region="us-east-1",
        )

        # Mock JWT payload with wrong issuer
        current_time = time.time()
        future_time = int(current_time + 3600)
        mock_payload = {
            "sub": "user-id-123",
            "exp": future_time,
            "iss": "https://wrong-issuer.com",  # Wrong issuer
        }

        mock_public_key = "mock-public-key"

        with patch.object(
            verifier, "_get_verification_key", return_value=mock_public_key
        ):
            with patch.object(verifier.jwt, "decode", return_value=mock_payload):
                valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"

                result = await verifier.verify_token(valid_jwt)
                assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_missing_required_scopes(self):
        """Test token verification with missing required scopes."""
        verifier = AWSCognitoTokenVerifier(
            required_scopes=["openid", "admin"],  # Require admin scope
            user_pool_id="us-east-1_XXXXXXXXX",
            aws_region="us-east-1",
        )

        # Mock JWT payload without admin scope
        current_time = time.time()
        future_time = int(current_time + 3600)
        mock_payload = {
            "sub": "user-id-123",
            "exp": future_time,
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXXXXX",
            "scope": "openid email",  # Missing admin scope
        }

        mock_public_key = "mock-public-key"

        with patch.object(
            verifier, "_get_verification_key", return_value=mock_public_key
        ):
            with patch.object(verifier.jwt, "decode", return_value=mock_payload):
                valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"

                result = await verifier.verify_token(valid_jwt)
                assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_jwt_decode_error(self):
        """Test token verification with JWT decode error."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        mock_public_key = "mock-public-key"

        with patch.object(
            verifier, "_get_verification_key", return_value=mock_public_key
        ):
            with patch.object(
                verifier.jwt, "decode", side_effect=JoseError("Invalid signature")
            ):
                valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"

                result = await verifier.verify_token(valid_jwt)
                assert result is None

    @pytest.mark.asyncio
    async def test_jwks_caching(self):
        """Test that JWKS responses are cached properly."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        mock_jwks = {
            "keys": [
                {
                    "kid": "test-kid",
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": "test-modulus",
                    "e": "AQAB",
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = mock_jwks
            mock_client.get.return_value = mock_response

            # Mock JsonWebKey.import_key to return a mock key
            with patch("fastmcp.server.auth.providers.aws.JsonWebKey") as mock_jwk:
                mock_key = MagicMock()
                mock_key.get_public_key.return_value = "mock-public-key"
                mock_jwk.import_key.return_value = mock_key

                # First call should fetch JWKS
                result1 = await verifier._get_jwks_key("test-kid")
                assert result1 == "mock-public-key"
                assert mock_client.get.call_count == 1

                # Second call should use cache (no additional HTTP request)
                result2 = await verifier._get_jwks_key("test-kid")
                assert result2 == "mock-public-key"
                assert mock_client.get.call_count == 1  # Still only one call
