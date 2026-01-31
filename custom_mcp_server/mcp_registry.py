"""
MCP Server Registry - Central configuration for all Activ8-AI MCP servers

This module provides:
1. Registry of all available MCP servers (local and external)
2. Use case mapping
3. Unified client configuration
4. Health checking and failover
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ServerType(Enum):
    """Type of MCP server deployment."""
    LOCAL_MEMORY = "local_memory"      # In-process, for testing
    LOCAL_STDIO = "local_stdio"        # Local Python script via STDIO
    LOCAL_HTTP = "local_http"          # Local HTTP server
    REMOTE_HTTP = "remote_http"        # Remote HTTP server
    NPX = "npx"                        # NPX package


class UseCase(Enum):
    """Use case categories for MCP servers."""
    DEVELOPMENT = "development"        # Dev tools, file ops, system info
    PROJECT_MGMT = "project_mgmt"      # Teamwork, task tracking
    DOCUMENTATION = "documentation"    # Notion, docs
    SOCIAL_MEDIA = "social_media"      # ATProto/Bluesky
    SMART_HOME = "smart_home"          # IoT, home automation
    MEMORY = "memory"                  # AI memory, embeddings
    TESTING = "testing"                # Echo servers, test utilities


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    description: str
    server_type: ServerType
    use_cases: list[UseCase]

    # Connection details (varies by server_type)
    script_path: str | None = None          # For LOCAL_STDIO
    http_url: str | None = None             # For LOCAL_HTTP/REMOTE_HTTP
    npx_package: str | None = None          # For NPX

    # Authentication
    env_vars: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    # Runtime
    port: int | None = None
    enabled: bool = True
    requires_auth: bool = False

    def to_client_config(self) -> dict[str, Any]:
        """Convert to FastMCP Client configuration format."""
        if self.server_type == ServerType.LOCAL_STDIO:
            return {
                "command": "python",
                "args": [self.script_path],
                "env": self.env_vars,
            }
        elif self.server_type in (ServerType.LOCAL_HTTP, ServerType.REMOTE_HTTP):
            config = {"url": self.http_url}
            if self.headers:
                config["headers"] = self.headers
            return config
        elif self.server_type == ServerType.NPX:
            return {
                "command": "npx",
                "args": [self.npx_package] + self._build_npx_args(),
                "env": self.env_vars,
            }
        return {}

    def _build_npx_args(self) -> list[str]:
        """Build NPX command arguments from env vars."""
        args = []
        for key, val in self.env_vars.items():
            # Convert ENV_VAR to --env-var format
            arg_name = key.lower().replace("_", "-")
            args.extend([f"--{arg_name}", val])
        return args


# =============================================================================
# ACTIV8-AI MCP SERVER REGISTRY
# =============================================================================

MCP_SERVERS: dict[str, MCPServerConfig] = {

    # -------------------------------------------------------------------------
    # LOCAL SERVERS (in this repo)
    # -------------------------------------------------------------------------

    "custom": MCPServerConfig(
        name="CustomMCP",
        description="Internal tools: system info, file ops, safe commands, calculations",
        server_type=ServerType.LOCAL_STDIO,
        use_cases=[UseCase.DEVELOPMENT, UseCase.TESTING],
        script_path="custom_mcp_server/server.py",
        enabled=True,
    ),

    "echo": MCPServerConfig(
        name="Echo Server",
        description="Simple echo server for testing MCP connections",
        server_type=ServerType.LOCAL_STDIO,
        use_cases=[UseCase.TESTING],
        script_path="examples/echo.py",
        enabled=True,
    ),

    "memory": MCPServerConfig(
        name="Memory Server",
        description="AI memory system with embeddings and pgvector",
        server_type=ServerType.LOCAL_STDIO,
        use_cases=[UseCase.MEMORY, UseCase.DEVELOPMENT],
        script_path="examples/memory.py",
        requires_auth=True,
        env_vars={
            "OPENAI_API_KEY": "${OPENAI_API_KEY}",  # Placeholder
        },
        enabled=False,  # Requires PostgreSQL + pgvector setup
    ),

    "smart_home": MCPServerConfig(
        name="Smart Home Hub",
        description="Philips Hue and home automation control",
        server_type=ServerType.LOCAL_STDIO,
        use_cases=[UseCase.SMART_HOME],
        script_path="examples/smart_home/src/smart_home/hub.py",
        requires_auth=True,
        env_vars={
            "HUE_BRIDGE_IP": "${HUE_BRIDGE_IP}",
            "HUE_BRIDGE_USERNAME": "${HUE_BRIDGE_USERNAME}",
        },
        enabled=False,  # Requires Hue bridge setup
    ),

    "atproto": MCPServerConfig(
        name="ATProto MCP",
        description="Bluesky social media: posts, likes, follows, search",
        server_type=ServerType.LOCAL_STDIO,
        use_cases=[UseCase.SOCIAL_MEDIA],
        script_path="examples/atproto_mcp/src/atproto_mcp/server.py",
        requires_auth=True,
        env_vars={
            "ATPROTO_HANDLE": "${ATPROTO_HANDLE}",
            "ATPROTO_PASSWORD": "${ATPROTO_PASSWORD}",
        },
        enabled=False,  # Requires Bluesky credentials
    ),

    # -------------------------------------------------------------------------
    # EXTERNAL SERVERS (other Activ8-AI repos)
    # -------------------------------------------------------------------------

    "teamwork": MCPServerConfig(
        name="Teamwork MCP",
        description="Project management: tasks, projects, people, time tracking",
        server_type=ServerType.NPX,
        use_cases=[UseCase.PROJECT_MGMT],
        npx_package="@vizioz/teamwork-mcp",
        requires_auth=True,
        env_vars={
            "TEAMWORK_DOMAIN": "${TEAMWORK_DOMAIN}",
            "TEAMWORK_USER": "${TEAMWORK_USER}",
            "TEAMWORK_PASS": "${TEAMWORK_PASS}",
        },
        enabled=False,  # Enable after configuring credentials
    ),

    "notion": MCPServerConfig(
        name="Notion MCP",
        description="Notion workspace: pages, databases, search, comments",
        server_type=ServerType.NPX,
        use_cases=[UseCase.DOCUMENTATION],
        npx_package="@notionhq/notion-mcp-server",
        requires_auth=True,
        env_vars={
            "NOTION_TOKEN": "${NOTION_TOKEN}",
        },
        enabled=False,  # Enable after configuring credentials
    ),

    # -------------------------------------------------------------------------
    # OFFICIAL FASTMCP DOCS (read-only reference)
    # -------------------------------------------------------------------------

    "fastmcp_docs": MCPServerConfig(
        name="FastMCP Docs",
        description="Search FastMCP documentation",
        server_type=ServerType.REMOTE_HTTP,
        use_cases=[UseCase.DOCUMENTATION, UseCase.DEVELOPMENT],
        http_url="https://gofastmcp.com/mcp",
        enabled=True,
    ),
}


def get_servers_by_use_case(use_case: UseCase) -> list[MCPServerConfig]:
    """Get all servers that support a given use case."""
    return [
        server for server in MCP_SERVERS.values()
        if use_case in server.use_cases and server.enabled
    ]


def get_enabled_servers() -> dict[str, MCPServerConfig]:
    """Get all enabled servers."""
    return {k: v for k, v in MCP_SERVERS.items() if v.enabled}


def build_multi_server_config(server_names: list[str] | None = None) -> dict[str, Any]:
    """
    Build a FastMCP Client multi-server configuration.

    Args:
        server_names: List of server names to include, or None for all enabled

    Returns:
        Configuration dict for FastMCP Client
    """
    if server_names is None:
        servers = get_enabled_servers()
    else:
        servers = {k: MCP_SERVERS[k] for k in server_names if k in MCP_SERVERS}

    return {
        "mcpServers": {
            name: config.to_client_config()
            for name, config in servers.items()
            if config.enabled
        }
    }


def print_registry():
    """Print a summary of all registered MCP servers."""
    print("\n" + "=" * 70)
    print("ACTIV8-AI MCP SERVER REGISTRY")
    print("=" * 70)

    for name, config in MCP_SERVERS.items():
        status = "✅ ENABLED" if config.enabled else "⚪ DISABLED"
        auth = "🔐" if config.requires_auth else "  "
        print(f"\n{status} {auth} {name}")
        print(f"    {config.description}")
        print(f"    Type: {config.server_type.value}")
        print(f"    Use cases: {', '.join(uc.value for uc in config.use_cases)}")

        if config.requires_auth and config.env_vars:
            missing = [k for k, v in config.env_vars.items() if v.startswith("${")]
            if missing:
                print(f"    ⚠️  Missing env vars: {', '.join(missing)}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    print_registry()
