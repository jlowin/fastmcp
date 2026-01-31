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
