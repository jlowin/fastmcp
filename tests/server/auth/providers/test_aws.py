"""Unit tests for AWS Cognito OAuth provider."""

import os
import time
from unittest.mock import patch

import pytest

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

        # Mock the parent JWTVerifier's verify_token to return None (simulating failure)
        with patch.object(
            verifier.__class__.__bases__[0], "verify_token", return_value=None
        ):
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

        valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"

        # Create a mock AccessToken that the parent JWTVerifier would return
        from fastmcp.server.auth.auth import AccessToken

        mock_access_token = AccessToken(
            token=valid_jwt,  # Use the actual token from the test
            client_id="cognito-client-id",
            scopes=["openid", "email"],
            expires_at=future_time,
            claims=mock_payload,
        )

        # Mock the parent's verify_token method to return the mock token
        with patch.object(
            verifier.__class__.__bases__[0],
            "verify_token",
            return_value=mock_access_token,
        ):
            result = await verifier.verify_token(valid_jwt)

            assert result is not None
            assert result.token == valid_jwt
            assert result.client_id == "cognito-client-id"
            assert result.scopes == ["openid", "email"]
            assert result.expires_at == future_time
            assert result.claims["sub"] == "user-id-123"
            assert result.claims["username"] == "testuser"
            assert result.claims["cognito:groups"] == ["admin", "users"]
            # Email and name should not be in filtered claims
            assert "email" not in result.claims
            assert "name" not in result.claims

    @pytest.mark.asyncio
    async def test_verify_token_expired(self):
        """Test token verification with expired token."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        # Mock the parent's verify_token to return None (expired token case)
        with patch.object(
            verifier.__class__.__bases__[0], "verify_token", return_value=None
        ):
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

        # Mock the parent's verify_token to return None (wrong issuer case)
        with patch.object(
            verifier.__class__.__bases__[0], "verify_token", return_value=None
        ):
            valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.signature"

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

        # Mock the parent's verify_token to return None (missing required scopes case)
        with patch.object(
            verifier.__class__.__bases__[0], "verify_token", return_value=None
        ):
            valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.signature"

            result = await verifier.verify_token(valid_jwt)
            assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_jwt_decode_error(self):
        """Test token verification with JWT decode error."""
        verifier = AWSCognitoTokenVerifier(
            user_pool_id="us-east-1_XXXXXXXXX",
        )

        # Mock the parent's verify_token to return None (JWT decode error case)
        with patch.object(
            verifier.__class__.__bases__[0], "verify_token", return_value=None
        ):
            valid_jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2lkIn0.signature"

            result = await verifier.verify_token(valid_jwt)
            assert result is None

    # JWKS caching is now handled by the parent JWTVerifier class
