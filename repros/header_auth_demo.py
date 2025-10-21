"""Demo: Per-request authentication using custom headers in FastMCP

This demonstrates how a centrally hosted MCP server could extract user identity
from HTTP headers on each request, enabling multi-tenant scenarios where:
1. Users connect via mcp-remote with custom headers (e.g., --header "X-Prefect-Api-Key: ${API_KEY}")
2. Server extracts credentials from headers per-request
3. Server uses those credentials to make authenticated API calls

This is the pattern needed for a globally hosted Prefect MCP where users
provide their own Prefect API URL/key without deploying their own server.
"""

from typing import Any

import mcp.types as mt

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


# Simulated external API that requires credentials
class PrefectAPI:
    """Simulates Prefect API that requires API URL + key"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    def get_flows(self) -> list[dict]:
        """Simulated API call"""
        return [
            {"id": "flow-1", "name": "ETL Pipeline", "api_url": self.api_url},
            {"id": "flow-2", "name": "Data Processing", "api_url": self.api_url},
        ]


# Custom middleware that extracts credentials from headers
class HeaderAuthMiddleware(Middleware):
    """Extracts authentication info from HTTP headers and makes it available to tools"""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, Any],
    ) -> Any:
        # Access the FastMCP context which contains the raw request
        fastmcp_ctx = context.fastmcp_context

        if fastmcp_ctx:
            print(f"[Middleware] Processing tool call: {context.message.params.name}")

            # Extract headers using the fastmcp.server.dependencies function
            try:
                headers = get_http_headers(include_all=True)
                print(f"[Middleware] Found {len(headers)} HTTP headers")

                # Extract auth credentials from custom headers
                api_url = headers.get("x-prefect-api-url")
                api_key = headers.get("x-prefect-api-key")

                if api_url and api_key:
                    fastmcp_ctx.set_state(
                        "auth_info", {"api_url": api_url, "api_key": api_key}
                    )
                    print(f"[Middleware] ✅ Extracted auth from headers: {api_url}")
                else:
                    print("[Middleware] ⚠️  No auth headers found, using defaults")
                    # Fallback to simulated values for testing
                    fastmcp_ctx.set_state(
                        "auth_info",
                        {
                            "api_url": "https://api.prefect.cloud/default",
                            "api_key": "pnu_simulated_key_no_headers",
                        },
                    )

            except RuntimeError as e:
                # Not running in HTTP mode (e.g., stdio transport)
                print(f"[Middleware] ⚠️  Not in HTTP mode: {e}")
                # Set simulated values for stdio testing
                fastmcp_ctx.set_state(
                    "auth_info",
                    {
                        "api_url": "https://api.prefect.cloud/stdio-mode",
                        "api_key": "pnu_simulated_key_stdio",
                    },
                )

        return await call_next(context)


# Create FastMCP app with middleware
mcp = FastMCP("Header Auth Demo")

# Add the custom middleware
middleware = HeaderAuthMiddleware()
mcp.add_middleware(middleware)


@mcp.tool()
def get_my_flows() -> str:
    """Get flows for the authenticated user (using credentials from request headers)"""
    from fastmcp.server.dependencies import get_context

    # Access the current request context
    ctx = get_context()

    # Extract auth info that was set by middleware
    auth_info = ctx.get_state("auth_info")

    if not auth_info:
        return "❌ No authentication info found in request headers!"

    # Create API client with per-request credentials
    api = PrefectAPI(api_url=auth_info["api_url"], api_key=auth_info["api_key"])

    # Make authenticated API call
    flows = api.get_flows()

    result = (
        f"✅ Found {len(flows)} flows for user with API URL: {auth_info['api_url']}\n\n"
    )
    for flow in flows:
        result += f"- {flow['name']} (ID: {flow['id']})\n"

    return result


@mcp.tool()
def show_auth_context() -> str:
    """Show what authentication info was extracted from headers"""
    from fastmcp.server.dependencies import get_context

    ctx = get_context()
    auth_info = ctx.get_state("auth_info")

    if not auth_info:
        return "❌ No authentication info in context"

    return f"""
✅ Authentication Info Extracted:
- API URL: {auth_info.get("api_url", "not set")}
- API Key: {auth_info.get("api_key", "not set")[:20]}... (truncated)

This info would normally come from HTTP headers like:
  X-Prefect-Api-Url: {auth_info.get("api_url")}
  X-Prefect-Api-Key: {auth_info.get("api_key")}
"""


if __name__ == "__main__":
    # Run the server
    print("\n🚀 Header Auth Demo Server\n")
    print("This demonstrates per-request authentication via headers.")
    print("In production, users would connect via mcp-remote with:")
    print('  --header "X-Prefect-Api-Url: ${PREFECT_API_URL}"')
    print('  --header "X-Prefect-Api-Key: ${PREFECT_API_KEY}"')
    print("\n")

    mcp.run()
