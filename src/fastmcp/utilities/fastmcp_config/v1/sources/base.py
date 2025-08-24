from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BaseSource(BaseModel, ABC):
    """Abstract base class for all source types."""

    type: str = Field(description="Source type identifier")

    async def prepare(self, config_path: Path | None = None) -> Path | None:
        """Prepare the source (download, clone, install, etc).

        Returns:
            Path to prepared source directory, or None if no preparation needed.
            This path may contain a nested fastmcp.json for configuration chaining.
        """
        # Default implementation for sources that don't need preparation
        return None

    @abstractmethod
    async def load_server(
        self, config_path: Path | None = None, server_args: list[str] | None = None
    ) -> Any:
        """Load and return the FastMCP server instance.

        Must be called after prepare() if the source requires preparation.
        """
        ...
