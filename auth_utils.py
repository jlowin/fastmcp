# ruff: noqa: BLE001, TRY002
"""
Authentication utilities for MCP Tools

This module provides authentication functionality for MCP tools to work with
the FastAPI backend. It handles JWT token validation and user authentication.
"""

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx


class MCPAuthenticator:
    """Handles authentication for MCP tools"""

    def __init__(self, backend_url: str = None):
        self.backend_url = backend_url or os.getenv(
            "BACKEND_URL", "https://full-stack-fastapi-template-bvfx.onrender.com"
        )

    async def get_jwt_token(self, email: str, password: str) -> str | None:
        """
        Get a JWT token by logging in with email/password
        """
        login_url = f"{self.backend_url}/api/v1/login/access-token"

        login_data = {
            "username": email,  # OAuth2 uses 'username' field
            "password": password,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    login_url,
                    data=login_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code == 200:
                    token_data = response.json()
                    return token_data.get("access_token")
                else:
                    print(f"Login failed: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            print(f"Login error: {e}")
            return None

    def decode_token(self, token: str) -> dict[str, Any] | None:
        """
        Decode JWT token to get user information (without verification for MCP)
        """
        try:
            # The backend verifies signatures. We only decode the JWT payload to
            # inspect expiry and identify the user for MCP convenience methods.
            _, payload, _ = token.split(".")
            padded_payload = payload + "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(padded_payload))
        except Exception as e:
            print(f"Token decode error: {e}")
            return None

    def is_token_valid(self, token: str) -> bool:
        """
        Check if token is still valid (not expired)
        """
        payload = self.decode_token(token)
        if not payload:
            return False

        exp = payload.get("exp")
        if not exp:
            return False

        # Check if token is expired
        return datetime.now(timezone.utc).timestamp() < exp

    async def validate_token_with_backend(self, token: str) -> dict[str, Any] | None:
        """
        Validate token with backend and get user info
        """
        me_url = f"{self.backend_url}/api/v1/users/me"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(me_url, headers=headers)

                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Token validation failed: {response.status_code}")
                    return None

        except Exception as e:
            print(f"Token validation error: {e}")
            return None


# Singleton authenticator instance
_authenticator = MCPAuthenticator()


async def get_default_jwt_token() -> str | None:
    """
    Get a default JWT token using environment credentials
    """
    email = os.getenv("FIRST_SUPERUSER", "test@example.com")
    password = os.getenv("FIRST_SUPERUSER_PASSWORD", "password123")

    return await _authenticator.get_jwt_token(email, password)


async def make_authenticated_request(
    method: str,
    endpoint: str,
    token: str,
    data: dict | None = None,
    params: dict | None = None,
) -> dict[str, Any]:
    """
    Make an authenticated request to the FastAPI backend using proper JWT token.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint (e.g., "/api/v1/notes/")
        token: JWT token for authentication
        data: Request body data (for POST/PUT)
        params: Query parameters

    Returns:
        Response data as dictionary

    Raises:
        Exception: If request fails
    """
    base_url = os.getenv(
        "BACKEND_URL", "https://full-stack-fastapi-template-bvfx.onrender.com"
    )
    url = f"{base_url}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=data,
                params=params,
            )

            # Check for authentication errors
            if response.status_code == 401:
                raise Exception("Authentication failed: Invalid or expired token")
            elif response.status_code == 403:
                raise Exception("Authorization failed: Insufficient permissions")
            elif response.status_code == 429:
                raise Exception("Rate limit exceeded: Too many requests")
            elif response.status_code >= 400:
                # Try to get error message from response
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", f"HTTP {response.status_code}")
                except ValueError:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                raise Exception(f"Request failed: {error_msg}")

            return response.json()

    except httpx.RequestError as e:
        raise Exception(f"Network error: {str(e)}")
    except Exception as e:
        # Re-raise our custom exceptions
        if (
            "Authentication failed" in str(e)
            or "Authorization failed" in str(e)
            or "Rate limit" in str(e)
        ):
            raise
        # Wrap other exceptions
        raise Exception(f"Request error: {str(e)}")


def get_user_id_from_token(token: str) -> str | None:
    """
    Extract user ID from JWT token
    """
    payload = _authenticator.decode_token(token)
    if payload:
        return payload.get("sub")  # 'sub' (subject) contains user ID
    return None


# For backwards compatibility - these functions convert user_id to proper JWT token
async def convert_user_id_to_token(user_id: str) -> str:
    """
    Convert user_id parameter to proper JWT token.

    For now, if user_id looks like a JWT token, use it directly.
    Otherwise, try to get a default token.
    """
    # Check if user_id is already a JWT token (contains dots)
    if user_id and "." in user_id and len(user_id) > 50:
        return user_id

    # Try to get default token
    token = await get_default_jwt_token()
    if token:
        return token

    # If all else fails, return the user_id (will likely fail but provides feedback)
    return user_id
