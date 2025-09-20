"""Persistent storage for OAuth client registrations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mcp.shared.auth import OAuthClientInformationFull
from pydantic import ValidationError

from fastmcp import settings as fastmcp_global_settings
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.storage import JSONFileStorage

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


def default_oauth_proxy_cache_dir() -> Path:
    """Default cache directory for OAuth proxy client storage."""
    return fastmcp_global_settings.home / "oauth-proxy-clients"


class OAuthClientStorage:
    """Persistent storage for OAuth client registrations.

    This class provides file-based storage for OAuth client information,
    allowing client registrations to persist across server restarts.

    Each client is stored as a separate JSON file, with the client_id
    used as the filename (after sanitization).

    Args:
        cache_dir: Directory for storing client data.
                  Defaults to ~/.fastmcp/oauth-proxy-clients/
    """

    def __init__(self, cache_dir: Path | None = None):
        """Initialize OAuth client storage."""
        self.cache_dir = cache_dir or default_oauth_proxy_cache_dir()
        self.storage = JSONFileStorage(self.cache_dir, prefix="client")

    async def get_client(
        self, client_id: str, allowed_redirect_uri_patterns: list[str] | None = None
    ) -> OAuthClientInformationFull | None:
        """Load client information from storage.

        Args:
            client_id: The client ID to retrieve
            allowed_redirect_uri_patterns: Patterns for ProxyDCRClient validation

        Returns:
            The client information or None if not found
        """
        try:
            data = await self.storage.get(client_id)
            if data is None:
                return None

            # Check if this is a ProxyDCRClient (has the special flag we'll add)
            is_proxy_client = data.get("_is_proxy_dcr_client", False)

            if is_proxy_client:
                # Import here to avoid circular dependency
                from fastmcp.server.auth.oauth_proxy import ProxyDCRClient

                # Remove the flag before creating the object
                data.pop("_is_proxy_dcr_client", None)

                # Create ProxyDCRClient with validation patterns
                return ProxyDCRClient(
                    allowed_redirect_uri_patterns=allowed_redirect_uri_patterns,
                    **data,
                )
            else:
                # Regular OAuthClientInformationFull
                return OAuthClientInformationFull(**data)  # type: ignore[missing-argument]

        except (ValidationError, TypeError) as e:
            logger.warning(f"Failed to load client {client_id}: {e}")
            return None

    async def save_client(
        self, client: OAuthClientInformationFull, is_proxy_dcr: bool = False
    ) -> None:
        """Save client information to storage.

        Args:
            client: The client information to save
            is_proxy_dcr: Whether this is a ProxyDCRClient (for special handling)
        """
        # Convert to dict for storage
        data = client.model_dump(mode="json")

        # Add flag if this is a ProxyDCRClient
        if is_proxy_dcr:
            data["_is_proxy_dcr_client"] = True

        await self.storage.set(client.client_id, data)
        logger.debug(f"Saved client {client.client_id} to persistent storage")

    async def delete_client(self, client_id: str) -> None:
        """Delete client information from storage.

        Args:
            client_id: The client ID to delete
        """
        await self.storage.delete(client_id)
        logger.debug(f"Deleted client {client_id} from persistent storage")

    async def clear_all(self) -> None:
        """Clear all stored client information."""
        await self.storage.clear()
        logger.info("Cleared all OAuth client registrations from storage")
