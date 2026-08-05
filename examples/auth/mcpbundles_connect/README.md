# MCPBundles Connect Auth Example

Demonstrates FastMCP server protection with [MCPBundles Connect Auth](https://www.mcpbundles.com/docs/integrations/mcp-connect-auth).

## Setup

### 1. Publish with MCP Connect Auth

1. Publish your MCP server on [MCPBundles](https://www.mcpbundles.com/mcp-analysis?intent=publish&connect_auth=1).
2. Enable **MCPBundles MCP client authentication** on the listing.
3. Configure federation sign-in URL and federation secret in the maintainer dashboard.

Create a `.env` file (or export variables):

```bash
# Required
MCPBUNDLES_LISTING_SLUG=my-published-listing
BASE_URL=http://127.0.0.1:8000/

# Optional: point at staging API while testing
# MCPBUNDLES_PUBLIC_CONFIG_BASE_URL=https://api.staging.mcpbundles.com

# Optional: additional scopes tokens must include (comma-separated)
# MCPBUNDLES_REQUIRED_SCOPES=read,write
```

### 2. Run the example

Start the server:

```bash
# From this directory
uv run python server.py
```

The server starts on `http://127.0.0.1:8000/mcp` with MCPBundles Connect Auth enabled on your vendor origin.

Smoke-check the tenant metadata:

```bash
mcpbundles connect doctor --listing "$MCPBUNDLES_LISTING_SLUG" --surface origin --base-url "$BASE_URL"
```

Test with the OAuth client:

```bash
uv run python client.py
```

The client will:

1. Connect to the protected server
2. Detect OAuth requirements and open a browser for MCP client authentication
3. Complete the OAuth flow via the MCPBundles tenant authorization server
4. Call authenticated tools

## Path B (bundle URL only)

Clients can also connect via `https://mcp.mcpbundles.com/bundle/{slug}/` without running this server — federation only on your web app. See the [integration guide](https://www.mcpbundles.com/docs/integrations/mcp-connect-auth).
