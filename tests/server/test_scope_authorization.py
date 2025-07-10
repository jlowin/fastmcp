"""Test scope-based authorization for tools."""
from collections.abc import Generator
from typing import Any

import httpx
import pytest

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.auth.bearer import BearerAuth
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from fastmcp.utilities.tests import run_server_in_process
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware


@pytest.fixture(scope="module")
def rsa_key_pair() -> RSAKeyPair:
    """Generate a key pair for testing."""
    return RSAKeyPair.generate()


def run_mcp_server_with_scopes(
    public_key: str,
    host: str,
    port: int,
    auth_kwargs: dict[str, Any] | None = None,
    run_kwargs: dict[str, Any] | None = None,
) -> None:
    """Run an MCP server with scope-based authorization."""
    auth_provider = BearerAuthProvider(
        public_key=public_key,
        issuer="https://test.example.com",
        audience="test-scope",
        **(auth_kwargs or {}),
    )
    
    # Create server with error handling middleware
    mcp = FastMCP(
        name="Scope Test Server",
        auth=auth_provider,
        middleware=[ErrorHandlingMiddleware()],
    )
    
    @mcp.tool
    def public_tool(message: str) -> str:
        """A tool that anyone can use (no specific scope required)."""
        return f"Public: {message}"
    
    @mcp.tool(required_scope="read")
    def read_tool(data: str) -> str:
        """A tool that requires 'read' scope."""
        return f"Read: {data}"
    
    @mcp.tool(required_scope="write")
    def write_tool(data: str) -> str:
        """A tool that requires 'write' scope."""
        return f"Write: {data}"
    
    @mcp.tool(required_scope="admin")
    def admin_tool(action: str) -> str:
        """A tool that requires 'admin' scope."""
        return f"Admin: {action}"
    
    # Run the server
    mcp.run(host=host, port=port, **(run_kwargs or {}))


@pytest.fixture(scope="module")
def scope_server_url(rsa_key_pair: RSAKeyPair) -> Generator[str]:
    """Create a running MCP server with scope-based authorization."""
    with run_server_in_process(
        run_mcp_server_with_scopes,
        public_key=rsa_key_pair.public_key,
        run_kwargs=dict(transport="http"),
    ) as url:
        yield f"{url}/mcp/"


class TestScopeBasedAuthorization:
    """Test scope-based authorization for tool execution."""

    @pytest.mark.asyncio
    async def test_tool_with_sufficient_scope(self, scope_server_url: str, rsa_key_pair: RSAKeyPair):
        """Test that tools work when user has sufficient scope."""
        # Create a token with read scope
        token = rsa_key_pair.create_token(
            subject="test-user",
            issuer="https://test.example.com",
            audience="test-scope",
            scopes=["read"]
        )

        # Test that we can call the read tool
        async with Client(scope_server_url, auth=BearerAuth(token)) as client:
            result = await client.call_tool("read_tool", {"data": "test"})
            assert result.data == "Read: test"

    @pytest.mark.asyncio
    async def test_tool_with_insufficient_scope(self, scope_server_url: str, rsa_key_pair: RSAKeyPair):
        """Test that tools fail when user lacks required scope."""
        # Create a token with only read scope
        token = rsa_key_pair.create_token(
            subject="test-user",
            issuer="https://test.example.com",
            audience="test-scope",
            scopes=["read"]
        )

        # Test that we cannot call the write tool
        from fastmcp.exceptions import AuthorizationError
        
        with pytest.raises(AuthorizationError) as exc_info:
            async with Client(scope_server_url, auth=BearerAuth(token)) as client:
                await client.call_tool("write_tool", {"data": "test"})
        
        assert "Access denied" in str(exc_info.value)
        assert "requires scope 'write'" in str(exc_info.value)
        assert "only scopes ['read'] are available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_tool_with_multiple_scopes(self, scope_server_url: str, rsa_key_pair: RSAKeyPair):
        """Test that tools work when user has multiple scopes."""
        # Create a token with read and write scopes
        token = rsa_key_pair.create_token(
            subject="test-user",
            issuer="https://test.example.com",
            audience="test-scope",
            scopes=["read", "write"]
        )

        # Test that we can call both read and write tools
        async with Client(scope_server_url, auth=BearerAuth(token)) as client:
            read_result = await client.call_tool("read_tool", {"data": "test"})
            assert read_result.data == "Read: test"
            
            write_result = await client.call_tool("write_tool", {"data": "test"})
            assert write_result.data == "Write: test"

    @pytest.mark.asyncio
    async def test_tool_with_admin_scope(self, scope_server_url: str, rsa_key_pair: RSAKeyPair):
        """Test that admin tools require admin scope."""
        # Create a token with admin scope
        token = rsa_key_pair.create_token(
            subject="admin-user",
            issuer="https://test.example.com",
            audience="test-scope",
            scopes=["admin"]
        )

        # Test that we can call the admin tool
        async with Client(scope_server_url, auth=BearerAuth(token)) as client:
            result = await client.call_tool("admin_tool", {"action": "delete"})
            assert result.data == "Admin: delete"

    @pytest.mark.asyncio
    async def test_tool_scope_defaults_to_tool_name(self, scope_server_url: str, rsa_key_pair: RSAKeyPair):
        """Test that default scope is the tool name."""
        # Create a token with 'public_tool' scope (matches the tool name)
        token = rsa_key_pair.create_token(
            subject="test-user",
            issuer="https://test.example.com",
            audience="test-scope",
            scopes=["public_tool"]
        )

        # Test that we can call the public tool
        async with Client(scope_server_url, auth=BearerAuth(token)) as client:
            result = await client.call_tool("public_tool", {"message": "test"})
            assert result.data == "Public: test"

    @pytest.mark.asyncio
    async def test_unauthorized_access_denied(self, scope_server_url: str):
        """Test that unauthorized access is denied."""
        # Test without any authentication
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with Client(scope_server_url) as client:
                await client.call_tool("read_tool", {"data": "test"})
        
        assert exc_info.value.response.status_code == 401

    @pytest.mark.asyncio
    async def test_authentication_vs_authorization_errors(self, scope_server_url: str, rsa_key_pair: RSAKeyPair):
        """Test that authentication errors are distinct from authorization errors."""
        from fastmcp.exceptions import AuthorizationError
        
        # Test 1: Authentication error (invalid token)
        invalid_token = "invalid.jwt.token"
        with pytest.raises(httpx.HTTPStatusError) as auth_exc_info:
            async with Client(scope_server_url, auth=BearerAuth(invalid_token)) as client:
                await client.call_tool("read_tool", {"data": "test"})
        
        # Should be 401 Unauthorized for authentication failure
        assert auth_exc_info.value.response.status_code == 401
        
        # Test 2: Authorization error (valid token, insufficient scope)
        valid_token_wrong_scope = rsa_key_pair.create_token(
            subject="test-user",
            issuer="https://test.example.com",
            audience="test-scope",
            scopes=["read"]  # Has read but trying to call write
        )
        
        with pytest.raises(AuthorizationError) as authz_exc_info:
            async with Client(scope_server_url, auth=BearerAuth(valid_token_wrong_scope)) as client:
                await client.call_tool("write_tool", {"data": "test"})
        
        # Should be AuthorizationError with specific message
        assert "Access denied" in str(authz_exc_info.value)
        assert "requires scope 'write'" in str(authz_exc_info.value)
        
        # Test 3: Verify client can catch errors differently
        try:
            async with Client(scope_server_url, auth=BearerAuth("invalid")) as client:
                await client.call_tool("read_tool", {"data": "test"})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                auth_error_caught = True
            else:
                auth_error_caught = False
        except AuthorizationError:
            auth_error_caught = False
        
        try:
            async with Client(scope_server_url, auth=BearerAuth(valid_token_wrong_scope)) as client:
                await client.call_tool("write_tool", {"data": "test"})
        except httpx.HTTPStatusError:
            authz_error_caught = False
        except AuthorizationError:
            authz_error_caught = True
        
        assert auth_error_caught, "Should catch authentication error as HTTPStatusError 401"
        assert authz_error_caught, "Should catch authorization error as AuthorizationError" 