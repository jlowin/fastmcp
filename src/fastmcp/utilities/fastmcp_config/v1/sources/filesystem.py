from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from fastmcp.utilities.fastmcp_config.v1.sources.base import BaseSource


class FileSystemSource(BaseSource):
    """Source for local Python files."""

    type: Literal["filesystem"] = Field(default="filesystem", description="Source type")
    path: str = Field(description="Path to Python file containing the server")
    entrypoint: str | None = Field(
        default=None,
        description="Name of server instance or factory function (a no-arg function that returns a FastMCP server)",
    )

    async def load_server(
        self, config_path: Path | None = None, server_args: list[str] | None = None
    ) -> Any:
        """Load server from filesystem."""
        from fastmcp.cli.run import import_server_with_args

        # Resolve relative paths if config_path provided
        file_path = Path(self.path)
        if not file_path.is_absolute() and config_path:
            file_path = (config_path.parent / file_path).resolve()

        return await import_server_with_args(file_path, self.entrypoint, server_args)
