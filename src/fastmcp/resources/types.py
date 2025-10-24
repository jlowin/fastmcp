"""Concrete resource implementations."""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import anyio.to_thread
import httpx
import pydantic.json
from anyio import Path as AsyncPath
from pydantic import Field, ValidationInfo

from fastmcp.exceptions import ResourceError
from fastmcp.resources.resource import Resource
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class TextResource(Resource):
    """A resource that reads from a string."""

    text: str = Field(description="Text content of the resource")

    async def read(self) -> str:
        """Read the text content."""
        return self.text


class BinaryResource(Resource):
    """A resource that reads from bytes."""

    data: bytes = Field(description="Binary content of the resource")

    async def read(self) -> bytes:
        """Read the binary content."""
        return self.data


class FileResource(Resource):
    """A resource that reads from a file.

    Set is_binary=True to read file as binary data instead of text.
    """

    path: Path = Field(description="Path to the file")
    is_binary: bool = Field(
        default=False,
        description="Whether to read the file as binary data",
    )
    mime_type: str = Field(
        default="text/plain",
        description="MIME type of the resource content",
    )

    @pydantic.field_validator("path")
    @classmethod
    def validate_absolute_path(cls, path: Path) -> Path:
        """Ensure path is absolute."""
        if not path.is_absolute():
            raise ValueError("Path must be absolute")
        return path

    @pydantic.field_validator("is_binary")
    @classmethod
    def set_binary_from_mime_type(cls, is_binary: bool, info: ValidationInfo) -> bool:
        """Set is_binary based on mime_type if not explicitly set."""
        if is_binary:
            return True
        mime_type = info.data.get("mime_type", "text/plain")
        return not mime_type.startswith("text/")

    async def read(self) -> str | bytes:
        """Read the file content."""
        try:
            if self.is_binary:
                return await anyio.to_thread.run_sync(self.path.read_bytes)
            return await anyio.to_thread.run_sync(self.path.read_text)
        except Exception as e:
            raise ResourceError(f"Error reading file {self.path}") from e


class HttpResource(Resource):
    """A resource that reads from an HTTP endpoint."""

    url: str = Field(description="URL to fetch content from")
    mime_type: str = Field(
        default="application/json", description="MIME type of the resource content"
    )

    async def read(self) -> str | bytes:
        """Read the HTTP content."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url)
            response.raise_for_status()
            return response.text


class DirectoryResource(Resource):
    """A resource that lists files in a directory."""

    path: Path = Field(description="Path to the directory")
    recursive: bool = Field(
        default=False, description="Whether to list files recursively"
    )
    pattern: str | None = Field(
        default=None, description="Optional glob pattern to filter files"
    )
    mime_type: str = Field(
        default="application/json", description="MIME type of the resource content"
    )

    @pydantic.field_validator("path")
    @classmethod
    def validate_absolute_path(cls, path: Path) -> Path:
        """Ensure path is absolute."""
        if not path.is_absolute():
            raise ValueError("Path must be absolute")
        return path

    async def list_files(self) -> list[Path]:
        """List files in the directory."""
        async_path = AsyncPath(self.path)

        if not await async_path.exists():
            raise FileNotFoundError(f"Directory not found: {self.path}")
        if not await async_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.path}")

        try:
            if self.pattern:
                if self.recursive:
                    files = [Path(p) async for p in async_path.rglob(self.pattern)]
                else:
                    files = [Path(p) async for p in async_path.glob(self.pattern)]
            else:
                if self.recursive:
                    files = [Path(p) async for p in async_path.rglob("*")]
                else:
                    files = [Path(p) async for p in async_path.glob("*")]
            return files
        except Exception as e:
            raise ResourceError(f"Error listing directory {self.path}: {e}")

    async def read(self) -> str:  # Always returns JSON string
        """Read the directory listing."""
        try:
            files = await self.list_files()
            # Filter to only files (not directories) asynchronously
            file_list = []
            for f in files:
                async_file = AsyncPath(f)
                if await async_file.is_file():
                    file_list.append(str(f.relative_to(self.path)))
            return json.dumps({"files": file_list}, indent=2)
        except Exception as e:
            logger.exception("Error reading directory %s", self.path)
            raise ResourceError(f"Error reading directory {self.path}") from e
