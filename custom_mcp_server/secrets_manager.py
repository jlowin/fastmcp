"""
Secrets Manager - Unified access to secrets from multiple sources

Sources (in priority order):
1. Environment variables (local .env or CI)
2. GitHub Secrets (via CI environment)
3. Notion Secrets Registry (via API)

Usage:
    from secrets_manager import get_secret, load_secrets, SecretsConfig

    # Get a single secret
    api_key = get_secret("OPENAI_API_KEY")

    # Load all secrets for a specific service
    teamwork_secrets = load_secrets("teamwork")
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    _dotenv_available = True
except ImportError:
    _dotenv_available = False


@dataclass
class SecretDefinition:
    """Definition of a required secret."""
    name: str
    description: str
    required: bool = True
    default: str | None = None


@dataclass
class ServiceSecrets:
    """Secrets configuration for a service."""
    service_name: str
    secrets: list[SecretDefinition]
    notion_page_id: str | None = None  # Optional Notion page with secrets


# =============================================================================
# SECRET DEFINITIONS BY SERVICE
# These match the secrets configured in GitHub Actions
# =============================================================================

SECRETS_REGISTRY: dict[str, ServiceSecrets] = {
    # -------------------------------------------------------------------------
    # AI/LLM APIs (confirmed in GitHub Secrets)
    # -------------------------------------------------------------------------
    "openai": ServiceSecrets(
        service_name="OpenAI",
        secrets=[
            SecretDefinition("OPENAI_API_KEY", "OpenAI API key for GPT models (RepoAgent, etc.)"),
        ],
    ),
    "anthropic": ServiceSecrets(
        service_name="Anthropic",
        secrets=[
            SecretDefinition("ANTHROPIC_API_KEY", "Anthropic API key for Claude"),
            SecretDefinition("ANTHROPIC_API_KEY_FOR_CI", "Anthropic API key for CI workflows", required=False),
        ],
    ),

    # -------------------------------------------------------------------------
    # GitHub (confirmed in GitHub Secrets)
    # -------------------------------------------------------------------------
    "github": ServiceSecrets(
        service_name="GitHub",
        secrets=[
            SecretDefinition("GITHUB_TOKEN", "Default GitHub token (auto-provided in Actions)"),
            SecretDefinition("FASTMCP_GITHUB_TOKEN", "FastMCP GitHub token for API access"),
            SecretDefinition("FASTMCP_TEST_AUTH_GITHUB_CLIENT_ID", "OAuth client ID", required=False),
            SecretDefinition("FASTMCP_TEST_AUTH_GITHUB_CLIENT_SECRET", "OAuth client secret", required=False),
        ],
    ),

    # -------------------------------------------------------------------------
    # Marvin AI (confirmed in GitHub Secrets)
    # -------------------------------------------------------------------------
    "marvin": ServiceSecrets(
        service_name="Marvin AI",
        secrets=[
            SecretDefinition("MARVIN_APP_ID", "Marvin GitHub App ID"),
            SecretDefinition("MARVIN_APP_PRIVATE_KEY", "Marvin GitHub App private key"),
        ],
    ),

    # -------------------------------------------------------------------------
    # MCP Servers (need to add to GitHub Secrets)
    # -------------------------------------------------------------------------
    "teamwork": ServiceSecrets(
        service_name="Teamwork",
        secrets=[
            SecretDefinition("TEAMWORK_DOMAIN", "Teamwork subdomain"),
            SecretDefinition("TEAMWORK_USER", "Teamwork username/email"),
            SecretDefinition("TEAMWORK_PASS", "Teamwork password or API key"),
        ],
    ),
    "notion": ServiceSecrets(
        service_name="Notion",
        secrets=[
            SecretDefinition("NOTION_TOKEN", "Notion integration token"),
        ],
    ),
    "atproto": ServiceSecrets(
        service_name="ATProto/Bluesky",
        secrets=[
            SecretDefinition("ATPROTO_HANDLE", "Bluesky handle (e.g., you.bsky.social)"),
            SecretDefinition("ATPROTO_PASSWORD", "Bluesky app password"),
        ],
    ),
    "hue": ServiceSecrets(
        service_name="Philips Hue",
        secrets=[
            SecretDefinition("HUE_BRIDGE_IP", "Hue bridge IP address"),
            SecretDefinition("HUE_BRIDGE_USERNAME", "Hue API username"),
        ],
    ),
}


# =============================================================================
# GITHUB SECRETS SUMMARY (from .github/workflows/)
# =============================================================================
GITHUB_SECRETS_AVAILABLE = [
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY_FOR_CI",
    "FASTMCP_GITHUB_TOKEN",
    "FASTMCP_TEST_AUTH_GITHUB_CLIENT_ID",
    "FASTMCP_TEST_AUTH_GITHUB_CLIENT_SECRET",
    "GITHUB_TOKEN",  # Auto-provided
    "MARVIN_APP_ID",
    "MARVIN_APP_PRIVATE_KEY",
    "OPENAI_API_KEY",
]


def _load_dotenv_if_available():
    """Load .env file if python-dotenv is available."""
    if not _dotenv_available:
        return False

    # Try multiple locations
    locations = [
        Path.cwd() / ".env",
        Path.cwd() / "custom_mcp_server" / ".env",
        Path(__file__).parent / ".env",
    ]

    for env_path in locations:
        if env_path.exists():
            load_dotenv(env_path)
            return True
    return False


def get_secret(name: str, default: str | None = None) -> str | None:
    """
    Get a secret from available sources.

    Priority:
    1. Environment variable
    2. Default value

    Args:
        name: Secret name (e.g., "OPENAI_API_KEY")
        default: Default value if not found

    Returns:
        Secret value or None
    """
    _load_dotenv_if_available()
    return os.environ.get(name, default)


def get_secret_required(name: str) -> str:
    """Get a required secret, raising an error if not found."""
    value = get_secret(name)
    if value is None:
        raise ValueError(f"Required secret '{name}' not found. Set it as an environment variable or in .env")
    return value


def load_secrets(service: str) -> dict[str, str | None]:
    """
    Load all secrets for a specific service.

    Args:
        service: Service name (e.g., "teamwork", "notion")

    Returns:
        Dict of secret names to values
    """
    if service not in SECRETS_REGISTRY:
        raise ValueError(f"Unknown service: {service}. Available: {list(SECRETS_REGISTRY.keys())}")

    _load_dotenv_if_available()

    service_config = SECRETS_REGISTRY[service]
    secrets = {}

    for secret_def in service_config.secrets:
        value = os.environ.get(secret_def.name, secret_def.default)
        secrets[secret_def.name] = value

    return secrets


def check_secrets(service: str) -> tuple[bool, list[str]]:
    """
    Check if all required secrets for a service are configured.

    Returns:
        (all_present, missing_secrets)
    """
    if service not in SECRETS_REGISTRY:
        return False, [f"Unknown service: {service}"]

    _load_dotenv_if_available()

    service_config = SECRETS_REGISTRY[service]
    missing = []

    for secret_def in service_config.secrets:
        if secret_def.required:
            value = os.environ.get(secret_def.name)
            if not value:
                missing.append(secret_def.name)

    return len(missing) == 0, missing


def print_secrets_status():
    """Print status of all secrets."""
    _load_dotenv_if_available()

    print("\n" + "=" * 60)
    print("SECRETS STATUS")
    print("=" * 60)

    for service_name, config in SECRETS_REGISTRY.items():
        ok, missing = check_secrets(service_name)
        status = "✅" if ok else "❌"
        print(f"\n{status} {config.service_name}")

        for secret_def in config.secrets:
            value = os.environ.get(secret_def.name)
            if value:
                masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
                print(f"   ✅ {secret_def.name}: {masked}")
            else:
                req = "(required)" if secret_def.required else "(optional)"
                print(f"   ⚪ {secret_def.name}: not set {req}")

    print("\n" + "=" * 60)


# =============================================================================
# NOTION SECRETS REGISTRY (if you store secrets in Notion)
# =============================================================================

async def fetch_secrets_from_notion(page_id: str) -> dict[str, str]:
    """
    Fetch secrets from a Notion page/database.

    Requires NOTION_TOKEN to be set.

    Args:
        page_id: Notion page or database ID containing secrets

    Returns:
        Dict of secret names to values
    """
    notion_token = get_secret("NOTION_TOKEN")
    if not notion_token:
        raise ValueError("NOTION_TOKEN required to fetch secrets from Notion")

    # Use the Notion MCP or direct API
    try:
        from fastmcp import Client

        async with Client("https://notion-mcp.example.com/mcp") as client:
            # This assumes a Notion MCP server with a read_page tool
            result = await client.call_tool("read_page", {"page_id": page_id})
            # Parse secrets from page content
            # Implementation depends on how secrets are stored in Notion
            return {}
    except Exception as e:
        print(f"Failed to fetch secrets from Notion: {e}")
        return {}


if __name__ == "__main__":
    print_secrets_status()
