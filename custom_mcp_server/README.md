# Custom MCP Server

A reference implementation for running MCP servers locally and on the web with redundant connections.

## Quick Start

```bash
# Install dependencies (from repo root)
uv sync

# Run locally (STDIO)
uv run python custom_mcp_server/server.py

# Run as web server (HTTP)
uv run python custom_mcp_server/server.py --http --port 8000

# Test the client
uv run python custom_mcp_server/client.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application / LLM                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │   RedundantMCPClient  │
              │   (Failover Logic)    │
              └───────────┬───────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   In-Memory   │ │    STDIO      │ │     HTTP      │
│  (Testing)    │ │   (Local)     │ │    (Web)      │
└───────────────┘ └───────────────┘ └───────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
              ┌───────────────────────┐
              │    CustomMCP Server   │
              │   - System tools      │
              │   - File tools        │
              │   - Utility tools     │
              └───────────────────────┘
```

## Transports

| Transport | Use Case | Command |
|-----------|----------|---------|
| **In-Memory** | Unit tests, development | `Client(mcp_server)` |
| **STDIO** | Local processes, Claude Desktop | `uv run python server.py` |
| **HTTP** | Web deployment, remote access | `uv run python server.py --http` |

## Tools Available

| Tool | Description |
|------|-------------|
| `get_system_info` | OS, Python version, timestamp |
| `get_env_var` | Safe environment variable access |
| `list_directory` | List files/directories |
| `read_file` | Read text files (line-limited) |
| `run_command` | Safe shell commands (whitelist) |
| `calculate` | Math expression evaluation |

## Redundant Connection Example

```python
from client import RedundantMCPClient
from server import mcp

client = RedundantMCPClient(
    in_memory_server=mcp,                    # Priority 1: fastest
    stdio_script="./server.py",              # Priority 2: local
    http_url="http://localhost:8000/mcp",    # Priority 3: remote
)

await client.connect(preferred="memory")  # Tries in order until success
result = await client.call_tool("get_system_info", {})
await client.disconnect()
```

## Integration with External MCP

If you have an existing custom MCP elsewhere:

```python
from fastmcp import Client

# Connect to your external MCP
async with Client("http://your-mcp-server.com/mcp") as client:
    tools = await client.list_tools()
    result = await client.call_tool("your_tool", {"arg": "value"})
```

Or mount it into this server:

```python
from fastmcp import FastMCP

mcp = FastMCP("Combined")
mcp.mount("http://your-mcp-server.com/mcp", prefix="external")
# Now tools are: external_your_tool, external_other_tool, etc.
```

## Activ8-AI MCP Server Registry

The `mcp_registry.py` provides a central configuration for all Activ8-AI MCP servers:

| Server | Type | Use Case | Status |
|--------|------|----------|--------|
| **custom** | Local | Development, Testing | ✅ Enabled |
| **echo** | Local | Testing | ✅ Enabled |
| **memory** | Local | AI Memory | 🔐 Needs config |
| **smart_home** | Local | IoT | 🔐 Needs config |
| **atproto** | Local | Social Media | 🔐 Needs config |
| **teamwork** | NPX | Project Management | 🔐 Needs config |
| **notion** | NPX | Documentation | 🔐 Needs config |
| **fastmcp_docs** | Remote | Reference | ✅ Enabled |

## Activation CLI

```bash
# List all servers and status
uv run python custom_mcp_server/activate.py --list

# Test server connections
uv run python custom_mcp_server/activate.py --test custom
uv run python custom_mcp_server/activate.py --test-all

# Generate Claude Desktop config
uv run python custom_mcp_server/activate.py --claude-desktop

# Run server in HTTP mode
uv run python custom_mcp_server/activate.py --serve custom --port 8000

# Connect to multiple servers
uv run python custom_mcp_server/activate.py --connect custom teamwork
```

## Enabling Servers

To enable servers that require authentication, set environment variables:

```bash
# Teamwork
export TEAMWORK_DOMAIN="your-company"
export TEAMWORK_USER="email@example.com"
export TEAMWORK_PASS="password"

# Notion
export NOTION_TOKEN="secret_xxx"

# Bluesky/ATProto
export ATPROTO_HANDLE="you.bsky.social"
export ATPROTO_PASSWORD="app-password"
```

Then edit `mcp_registry.py` and set `enabled=True` for the servers you want to use.
