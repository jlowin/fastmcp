"""
Activ8-AI Unified MCP Registry

Central configuration for all Activ8-AI MCP servers.
Each server can run independently - this registry provides unified access.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ServerType(Enum):
    """Type of MCP server deployment."""
    NPX = "npx"                        # NPX package (TypeScript/Node)
    PYTHON = "python"                  # Python script
    DOCKER = "docker"                  # Docker container
    REMOTE = "remote"                  # Remote HTTP endpoint


class UseCase(Enum):
    """Use case categories for MCP servers."""
    PROJECT_MGMT = "project_mgmt"      # Teamwork, task tracking
    DOCUMENTATION = "documentation"    # Notion, docs
    WEB_SCRAPING = "web_scraping"      # Firecrawl, web data
    CONTAINERS = "containers"          # Docker Hub
    TERMINAL = "terminal"              # Shell, process control
    DEVELOPMENT = "development"        # Dev tools, utilities
    ANALYTICS = "analytics"            # Google Analytics, metrics


@dataclass
class MCPServer:
    """Configuration for an MCP server."""
    name: str
    repo: str                          # GitHub repo (Activ8-AI/...)
    description: str
    server_type: ServerType
    use_cases: list[UseCase]
    tools_count: int

    # Connection details
    npx_package: str | None = None     # For NPX servers
    docker_image: str | None = None    # For Docker servers

    # Authentication
    required_secrets: list[str] = field(default_factory=list)

    # Status
    enabled: bool = False
    maintained: bool = True            # Is this actively maintained?


# =============================================================================
# ACTIV8-AI MCP SERVER REGISTRY
# =============================================================================

MCP_REGISTRY: dict[str, MCPServer] = {

    # -------------------------------------------------------------------------
    # CORE SERVERS (actively used)
    # -------------------------------------------------------------------------

    "teamwork": MCPServer(
        name="Teamwork MCP",
        repo="Activ8-AI/Teamwork-MCP",
        description="Project management: tasks, projects, people, time tracking, reports",
        server_type=ServerType.NPX,
        use_cases=[UseCase.PROJECT_MGMT],
        tools_count=30,
        npx_package="@vizioz/teamwork-mcp",
        required_secrets=["TEAMWORK_DOMAIN", "TEAMWORK_USER", "TEAMWORK_PASS"],
        enabled=True,
        maintained=True,
    ),

    "notion": MCPServer(
        name="Notion MCP",
        repo="Activ8-AI/notion-mcp-server",
        description="Notion workspace: pages, databases, search, comments",
        server_type=ServerType.NPX,
        use_cases=[UseCase.DOCUMENTATION],
        tools_count=8,
        npx_package="@notionhq/notion-mcp-server",
        required_secrets=["NOTION_TOKEN"],
        enabled=True,
        maintained=True,
    ),

    "firecrawl": MCPServer(
        name="Firecrawl MCP",
        repo="Activ8-AI/firecrawl-mcp-server",
        description="Web scraping: scrape, crawl, map, search, extract structured data",
        server_type=ServerType.NPX,
        use_cases=[UseCase.WEB_SCRAPING],
        tools_count=7,
        npx_package="firecrawl-mcp",
        required_secrets=["FIRECRAWL_API_KEY"],
        enabled=True,
        maintained=True,
    ),

    "desktop_commander": MCPServer(
        name="Desktop Commander",
        repo="Activ8-AI/docker-Desktop-Commander-MCP",
        description="Terminal control, file ops, code execution, process management",
        server_type=ServerType.NPX,
        use_cases=[UseCase.TERMINAL, UseCase.DEVELOPMENT],
        tools_count=15,
        npx_package="desktop-commander",
        required_secrets=[],  # No auth needed for local
        enabled=True,
        maintained=True,
    ),

    # -------------------------------------------------------------------------
    # SECONDARY SERVERS (optional)
    # -------------------------------------------------------------------------

    "docker_hub": MCPServer(
        name="Docker Hub MCP",
        repo="Activ8-AI/hub-mcp",
        description="Docker Hub: search images, manage repos, tags",
        server_type=ServerType.NPX,
        use_cases=[UseCase.CONTAINERS],
        tools_count=10,
        npx_package="@docker/hub-mcp",
        required_secrets=["DOCKER_HUB_TOKEN"],
        enabled=False,
        maintained=True,
    ),

    "google_analytics": MCPServer(
        name="Google Analytics MCP",
        repo="Activ8-AI/google-analytics-mcp",
        description="GA4 reporting and analytics data access",
        server_type=ServerType.PYTHON,
        use_cases=[UseCase.ANALYTICS],
        tools_count=5,
        required_secrets=["GA_PROPERTY_ID", "GA_CREDENTIALS_JSON"],
        enabled=False,
        maintained=False,
    ),
}


# =============================================================================
# TOOL INVENTORY (what each server provides)
# =============================================================================

TOOL_INVENTORY = {
    "teamwork": {
        "projects": ["getProjects", "getCurrentProject", "createProject"],
        "tasks": ["getTasks", "getTaskById", "createTask", "updateTask", "deleteTask",
                  "getTaskSubtasks", "getTaskComments", "createSubTask"],
        "people": ["getPeople", "getPersonById", "getProjectPeople", "addPeopleToProject"],
        "time": ["getTime", "getProjectsAllocationsTime", "getTimezones"],
        "reports": ["getTasksMetricsComplete", "getTasksMetricsLate",
                    "getProjectsReportingUserTaskCompletion", "getProjectsReportingUtilization"],
    },
    "notion": {
        "pages": ["search", "get_page", "create_page", "append_blocks"],
        "databases": ["get_database", "query_database"],
        "comments": ["add_comment"],
    },
    "firecrawl": {
        "scraping": ["firecrawl_scrape", "firecrawl_batch_scrape", "firecrawl_crawl"],
        "discovery": ["firecrawl_map", "firecrawl_search"],
        "extraction": ["firecrawl_extract"],
        "status": ["firecrawl_check_batch_status"],
    },
    "desktop_commander": {
        "terminal": ["execute_command", "list_processes", "kill_process"],
        "files": ["read_file", "write_file", "list_directory", "move_file", "search_files"],
        "code": ["execute_code", "edit_file", "search_code"],
        "config": ["get_config", "set_config"],
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_enabled_servers() -> dict[str, MCPServer]:
    """Get all enabled servers."""
    return {k: v for k, v in MCP_REGISTRY.items() if v.enabled}


def get_servers_by_use_case(use_case: UseCase) -> list[MCPServer]:
    """Get servers for a specific use case."""
    return [s for s in MCP_REGISTRY.values() if use_case in s.use_cases and s.enabled]


def check_server_secrets(server_name: str) -> tuple[bool, list[str]]:
    """Check if required secrets are available for a server."""
    if server_name not in MCP_REGISTRY:
        return False, [f"Unknown server: {server_name}"]

    server = MCP_REGISTRY[server_name]
    missing = [s for s in server.required_secrets if not os.environ.get(s)]
    return len(missing) == 0, missing


def generate_claude_desktop_config() -> dict[str, Any]:
    """Generate configuration for Claude Desktop."""
    config = {"mcpServers": {}}

    for name, server in get_enabled_servers().items():
        if server.server_type == ServerType.NPX and server.npx_package:
            secrets_ok, _ = check_server_secrets(name)
            if secrets_ok or not server.required_secrets:
                config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", server.npx_package],
                    "env": {s: os.environ.get(s, "") for s in server.required_secrets},
                }

    return config


def print_registry():
    """Print registry summary."""
    print("\n" + "=" * 70)
    print("ACTIV8-AI MCP SERVER REGISTRY")
    print("=" * 70)

    for name, server in MCP_REGISTRY.items():
        if not server.maintained:
            status = "DEPRECATED"
        elif server.enabled:
            status = "ENABLED"
        else:
            status = "DISABLED"

        print(f"\n[{status}] {name}")
        print(f"    {server.description}")
        print(f"    Repo: {server.repo}")
        print(f"    Tools: {server.tools_count} | Type: {server.server_type.value}")

        if server.required_secrets:
            ok, missing = check_server_secrets(name)
            if missing:
                print(f"    Missing: {', '.join(missing)}")
            else:
                print("    Secrets configured")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    print_registry()
