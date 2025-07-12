#!/usr/bin/env python3
"""
Example demonstrating scope-based authorization in FastMCP.

This example shows how to use the required_scope parameter in tool decorators
to control access to specific tools based on OAuth scopes. It also demonstrates
how clients can distinguish between authentication and authorization errors.
"""

import httpx

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.auth.bearer import BearerAuth
from fastmcp.exceptions import AuthenticationError, AuthorizationError, ToolError
from fastmcp.server.auth import BearerAuthProvider
from fastmcp.server.auth.providers.bearer import RSAKeyPair
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware

# Generate a key pair for testing
key_pair = RSAKeyPair.generate()

# Configure bearer auth with the public key
auth = BearerAuthProvider(
    public_key=key_pair.public_key, issuer="https://example.com", audience="scope-demo"
)

# Create FastMCP server with authentication and error handling middleware
mcp = FastMCP(
    name="Scope Authorization Demo", auth=auth, middleware=[ErrorHandlingMiddleware()]
)


@mcp.tool
def public_tool(message: str) -> str:
    """A tool that anyone can use (no specific scope required)."""
    return f"Public response: {message}"


@mcp.tool(required_scope="read")
def read_data(query: str) -> str:
    """A tool that requires 'read' scope."""
    return f"Reading data: {query}"


@mcp.tool(required_scope="write")
def write_data(data: str) -> str:
    """A tool that requires 'write' scope."""
    return f"Writing data: {data}"


@mcp.tool(required_scope="admin")
def admin_action(action: str) -> str:
    """A tool that requires 'admin' scope."""
    return f"Admin action: {action}"


async def example_client_usage():
    """Demonstrate how clients can handle authentication vs authorization errors."""

    # Start the server (in real usage, this would be running separately)
    server_url = "http://localhost:8080/mcp/"

    print("=== Scope-based Authorization Example ===\n")

    # Example 1: Valid token with sufficient scope
    print("1. Testing with valid token and sufficient scope:")
    read_token = key_pair.create_token(
        subject="user-1",
        issuer="https://example.com",
        audience="scope-demo",
        scopes=["read", "write"],
    )

    try:
        async with Client(server_url, auth=BearerAuth(read_token)) as client:
            result = await client.call_tool("read_data", {"query": "test"})
            print(f"   ✓ Success: {result.data}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Example 2: Authentication error (invalid token)
    print("\n2. Testing with invalid token (authentication error):")
    try:
        async with Client(server_url, auth=BearerAuth("invalid.token")) as client:
            await client.call_tool("read_data", {"query": "test"})
    except AuthenticationError as e:
        print(f"   ✓ Caught authentication error: {e}")
        print(
            "   → Client should: Re-authenticate, refresh token, or redirect to login"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print(
                f"   ✓ Caught HTTP 401 authentication error: {e.response.status_code} {e.response.reason_phrase}"
            )
            print(
                "   → Client should: Re-authenticate, refresh token, or redirect to login"
            )
    except Exception as e:
        print(f"   ✗ Unexpected error: {e}")

    # Example 3: Authorization error (valid token, insufficient scope)
    print("\n3. Testing with valid token but insufficient scope (authorization error):")
    read_only_token = key_pair.create_token(
        subject="user-2",
        issuer="https://example.com",
        audience="scope-demo",
        scopes=["read"],  # Only has read, not write
    )

    try:
        async with Client(server_url, auth=BearerAuth(read_only_token)) as client:
            await client.call_tool("write_data", {"data": "test"})
    except AuthorizationError as e:
        print(f"   ✓ Caught authorization error: {e}")
        print(
            "   → Client should: Request additional scopes, show error to user, or disable feature"
        )
    except httpx.HTTPStatusError as e:
        print(f"   ✗ Unexpected HTTP error: {e.response.status_code}")
    except Exception as e:
        print(f"   ✗ Unexpected error: {e}")

    # Example 4: Comprehensive error handling pattern
    print("\n4. Comprehensive error handling pattern:")

    async def safe_tool_call(client, tool_name, arguments):
        """Example of comprehensive error handling for tool calls."""
        try:
            result = await client.call_tool(tool_name, arguments)
            return {"success": True, "data": result.data}

        except AuthenticationError as e:
            # Token is invalid, expired, or malformed
            return {"success": False, "error": "auth_required", "message": str(e)}

        except AuthorizationError as e:
            # Token is valid but lacks required scope
            return {"success": False, "error": "insufficient_scope", "message": str(e)}

        except ToolError as e:
            # General tool execution error
            return {"success": False, "error": "tool_error", "message": str(e)}

        except httpx.HTTPStatusError as e:
            # HTTP-level error (network, server issues)
            if e.response.status_code == 401:
                return {
                    "success": False,
                    "error": "auth_required",
                    "message": "Authentication required",
                }
            elif e.response.status_code == 403:
                return {
                    "success": False,
                    "error": "forbidden",
                    "message": "Access forbidden",
                }
            else:
                return {
                    "success": False,
                    "error": "http_error",
                    "message": f"HTTP {e.response.status_code}",
                }

        except Exception as e:
            # Unexpected error
            return {"success": False, "error": "unknown", "message": str(e)}

    # Test different error scenarios
    test_cases = [
        ("valid_token_sufficient_scope", read_token, "read_data", {"query": "test"}),
        ("invalid_token", "invalid.token", "read_data", {"query": "test"}),
        ("insufficient_scope", read_only_token, "admin_action", {"action": "delete"}),
    ]

    for test_name, token, tool_name, arguments in test_cases:
        print(f"\n   Testing {test_name}:")
        try:
            async with Client(server_url, auth=BearerAuth(token)) as client:
                result = await safe_tool_call(client, tool_name, arguments)
                if result["success"]:
                    print(f"      ✓ Success: {result['data']}")
                else:
                    print(f"      ✗ Error ({result['error']}): {result['message']}")
        except Exception as e:
            print(f"      ✗ Unexpected error: {e}")

    print("\n=== Error Handling Guidelines ===")
    print("• AuthenticationError: Invalid/expired token")
    print("  → Actions: Re-authenticate, refresh token, redirect to login")
    print("• AuthorizationError: Valid token, insufficient scope")
    print("  → Actions: Request additional scopes, disable feature, show error to user")
    print("• ToolError: General tool execution issues")
    print("  → Actions: Show error to user, log error, retry if appropriate")
    print("• HTTPStatusError: Network/server issues")
    print(
        "  → Actions: Handle by status code, implement retry logic for transient errors"
    )


if __name__ == "__main__":
    print("FastMCP Scope-based Authorization Example")
    print("=" * 50)
    print()
    print("This example demonstrates:")
    print("1. How to add scope requirements to tools")
    print("2. How to distinguish authentication vs authorization errors")
    print("3. Best practices for error handling in MCP clients")
    print()
    print("To run this example:")
    print("1. Start the server: python -m fastmcp.cli run scope_example:mcp")
    print("2. Connect clients with appropriate tokens")
    print("3. Observe different error types and handling patterns")

    # Uncomment to run the client example (requires running server)
    # import asyncio
    # asyncio.run(example_client_usage())
