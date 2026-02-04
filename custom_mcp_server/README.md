# Activ8-AI MCP Server

A unified MCP (Model Context Protocol) infrastructure for the Activ8-AI organization. Provides 21 tools across 10 categories plus a registry of all organization MCP servers.

## Quick Start

```bash
# Install (from this directory)
pip install -e .

# Or with uv
uv pip install -e .

# Run locally (STDIO) - for Claude Desktop
activ8-mcp serve

# Run as web server (HTTP)
activ8-mcp serve --http --port 8000

# List all registered servers
activ8-mcp list

# Generate Claude Desktop config
activ8-mcp config
```

## Tools Available (21 total)

| Category | Tools |
|----------|-------|
| **System** | `get_system_info`, `get_env_var` |
| **Files** | `list_directory`, `read_file` |
| **Utility** | `run_command`, `calculate` |
| **Git** | `git_status`, `git_diff` |
| **Search** | `search_files`, `find_files` |
| **JSON** | `parse_json`, `format_json` |
| **HTTP** | `http_get`, `check_url` |
| **Text** | `text_stats`, `regex_search`, `hash_text` |
| **Network** | `check_port`, `dns_lookup` |
| **DateTime** | `current_time`, `parse_timestamp` |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application / LLM                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │    Activ8-AI MCP      │
              │    Server + Registry  │
              └───────────┬───────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│    STDIO      │ │     HTTP      │ │   External    │
│ (Local/CLI)   │ │   (Web API)   │ │  MCP Servers  │
└───────────────┘ └───────────────┘ └───────────────┘
```

## MCP Server Registry

The `activ8_mcp.registry` module provides a unified registry of all Activ8-AI MCP servers:

| Server | Type | Tools | Use Case | Status |
|--------|------|-------|----------|--------|
| **teamwork** | NPX | 30 | Project Management | Enabled |
| **notion** | NPX | 8 | Documentation | Enabled |
| **firecrawl** | NPX | 7 | Web Scraping | Enabled |
| **desktop_commander** | NPX | 15 | Terminal/Dev | Enabled |
| **docker_hub** | NPX | 10 | Containers | Disabled |

```python
from activ8_mcp import MCP_REGISTRY, get_enabled_servers, get_servers_by_use_case, UseCase

# Get all enabled servers
enabled = get_enabled_servers()

# Get servers for a specific use case
project_servers = get_servers_by_use_case(UseCase.PROJECT_MGMT)
```

## Claude Desktop Integration

Generate configuration for Claude Desktop:

```bash
activ8-mcp config
```

This outputs JSON to add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "activ8": {
      "command": "activ8-mcp",
      "args": ["serve"]
    }
  }
}
```

## Environment Variables

For servers that require authentication, set these environment variables:

```bash
# Teamwork
export TEAMWORK_DOMAIN="your-company"
export TEAMWORK_USER="email@example.com"
export TEAMWORK_PASS="password"

# Notion
export NOTION_TOKEN="secret_..."

# Firecrawl
export FIRECRAWL_API_KEY="fc-..."
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .
```

## Package Structure

```
activ8-mcp/
├── pyproject.toml          # Package configuration
├── README.md               # This file
├── src/
│   └── activ8_mcp/
│       ├── __init__.py     # Package exports
│       ├── server.py       # MCP server with 21 tools
│       ├── registry.py     # Unified server registry
│       └── cli.py          # Command-line interface
└── tests/
    └── test_server.py      # Server tests
```

## Extraction to Standalone Repo

This package is designed to be extracted to its own repository:

```bash
# From parent directory
mkdir activ8-mcp
cp -r custom_mcp_server/* activ8-mcp/
cd activ8-mcp

# Initialize git
git init
git add .
git commit -m "Initial commit: Activ8-AI MCP Server"

# Push to new repo
git remote add origin git@github.com:Activ8-AI/activ8-mcp.git
git push -u origin main
```

## License

MIT
