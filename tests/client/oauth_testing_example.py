"""
Example: Testing FastMCP with Headless OAuth

This example demonstrates how to test OAuth-protected FastMCP servers
without browser interaction, perfect for automated testing and CI/CD.

Key Benefits:
- Real FastMCP Client and Server interaction
- Complete OAuth flow without browser
- No external dependencies
- Works in headless environments
"""

import asyncio
import sys
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import uvicorn

import fastmcp.client.auth  # Import module, not the function directly
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.auth import ClientRegistrationOptions
from fastmcp.server.auth.providers.in_memory import InMemory
from fastmcp.server.server import FastMCP
from fastmcp.utilities.tests import run_server_in_process


class HeadlessOAuthProvider(httpx.Auth):
    """OAuth provider that completes the OAuth flow programmatically."""

    def __init__(self, mcp_url: str):
        parsed_url = urlparse(mcp_url)
        self.server_base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        self._access_token = None

    async def async_auth_flow(self, request):
        """Add Bearer token to requests."""
        if not self._access_token:
            await self._obtain_token()
        if self._access_token:
            request.headers["Authorization"] = f"Bearer {self._access_token}"
        response = yield request

    async def _obtain_token(self):
        """Complete OAuth flow programmatically."""
        import base64
        import hashlib
        import secrets

        from mcp.shared.auth import OAuthClientInformationFull
        from pydantic import AnyHttpUrl

        # Generate PKCE challenge/verifier
        code_verifier = (
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        )
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        async with httpx.AsyncClient() as client:
            # 1. Discover OAuth metadata
            metadata_url = (
                f"{self.server_base_url}/.well-known/oauth-authorization-server"
            )
            response = await client.get(metadata_url)
            response.raise_for_status()
            metadata = response.json()

            # 2. Register client
            client_info = OAuthClientInformationFull(
                client_id="test_client",
                client_secret="test_secret",
                redirect_uris=[AnyHttpUrl("http://localhost:8080/callback")],
            )

            register_response = await client.post(
                metadata["registration_endpoint"],
                json=client_info.model_dump(
                    mode="json"
                ),  # Use mode="json" for proper serialization
            )
            register_response.raise_for_status()
            registered_client = register_response.json()

            # 3. Get authorization code
            auth_response = await client.get(
                metadata["authorization_endpoint"],
                params={
                    "response_type": "code",
                    "client_id": registered_client["client_id"],
                    "redirect_uri": "http://localhost:8080/callback",
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                    "state": "test_state",
                },
                follow_redirects=False,
            )

            if auth_response.status_code == 302:
                # Extract auth code from redirect
                redirect_url = auth_response.headers["location"]
                parsed = urlparse(redirect_url)
                query_params = parse_qs(parsed.query)

                if "error" in query_params:
                    error = query_params["error"][0]
                    error_desc = query_params.get(
                        "error_description", ["Unknown error"]
                    )[0]
                    raise RuntimeError(
                        f"OAuth authorization failed: {error} - {error_desc}"
                    )

                auth_code = query_params["code"][0]

                # 4. Exchange for access token
                token_response = await client.post(
                    metadata["token_endpoint"],
                    data={
                        "grant_type": "authorization_code",
                        "client_id": registered_client["client_id"],
                        "client_secret": registered_client["client_secret"],
                        "code": auth_code,
                        "redirect_uri": "http://localhost:8080/callback",
                        "code_verifier": code_verifier,  # Use the actual verifier
                    },
                )
                token_response.raise_for_status()
                token_info = token_response.json()
                self._access_token = token_info["access_token"]


def create_auth_server(issuer_url: str) -> FastMCP:
    """Create a FastMCP server with OAuth authentication."""
    server = FastMCP(
        "ExampleAuthServer",
        auth=InMemory(
            issuer_url=issuer_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        ),
    )

    @server.tool()
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    @server.resource("resource://secret")
    def get_secret() -> str:
        """Get a secret that requires authentication."""
        return "This is a secret message!"

    return server


def run_auth_server(host: str, port: int, transport: str | None = None) -> None:
    """Run the auth server in a subprocess."""
    try:
        issuer_url = f"http://{host}:{port}"
        app = create_auth_server(issuer_url).http_app()
        server = uvicorn.Server(
            config=uvicorn.Config(
                app=app,
                host=host,
                port=port,
                log_level="error",
                lifespan="on",
            )
        )
        server.run()
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)
    sys.exit(0)


async def main():
    """
    Example showing how to test OAuth-protected FastMCP with headless auth.
    """
    print("🚀 FastMCP Headless OAuth Testing Example")
    print("==========================================")

    # Start server in subprocess
    with run_server_in_process(run_auth_server) as server_url:
        mcp_url = f"{server_url}/mcp"
        print(f"📡 Server running at: {server_url}")

        # Create headless OAuth provider
        def headless_oauth(*args, **kwargs):
            # Get mcp_url from either positional or keyword arguments
            mcp_url = args[0] if args else kwargs.get("mcp_url")
            if not mcp_url:
                raise ValueError("mcp_url is required")
            return HeadlessOAuthProvider(mcp_url)

        # Patch OAuth to use headless provider
        with patch("fastmcp.client.auth.OAuth", side_effect=headless_oauth):
            # Create authenticated client using the module-qualified name
            client = Client(
                transport=StreamableHttpTransport(mcp_url),
                auth=fastmcp.client.auth.OAuth(mcp_url=mcp_url),  # Use module.function
            )

            print("🔐 Testing authenticated FastMCP client...")

            async with client:
                # Test tool calls
                print("\n📧 Testing tool calls:")
                tools = await client.list_tools()
                print(f"   Available tools: {[t.name for t in tools]}")

                result = await client.call_tool("multiply", {"a": 6, "b": 7})
                print(f"   multiply(6, 7) = {result[0].text}")  # type: ignore[attr-defined]

                # Test resource access
                print("\n📄 Testing resource access:")
                resources = await client.list_resources()
                print(f"   Available resources: {[str(r.uri) for r in resources]}")

                content = await client.read_resource("resource://secret")
                print(f"   Secret content: {content[0].text}")  # type: ignore[attr-defined]

            print("\n✅ All authenticated operations successful!")
            print("\n💡 This demonstrates testing OAuth-protected FastMCP")
            print("   servers without browser interaction - perfect for")
            print("   automated testing and CI/CD pipelines!")


if __name__ == "__main__":
    asyncio.run(main())
