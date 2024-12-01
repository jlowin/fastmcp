"""Base classes and interfaces for FastMCP resources."""

import abc
from typing import Union

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    FileUrl,
    ValidationInfo,
    field_validator,
)


class Resource(BaseModel, abc.ABC):
    """Base class for all resources."""

    model_config = ConfigDict(validate_default=True)

    # uri: Annotated[AnyUrl, BeforeValidator(maybe_cast_str_to_any_url)] = Field(
    uri: AnyUrl = Field(default=..., description="URI of the resource")
    name: str | None = Field(description="Name of the resource", default=None)
    description: str | None = Field(
        description="Description of the resource", default=None
    )
    mime_type: str | None = Field(
        default="text/plain",
        description="MIME type of the resource content",
        pattern=r"^[a-zA-Z0-9]+/[a-zA-Z0-9\-+.]+$",
    )

    @field_validator("uri", mode="before")
    def validate_uri(cls, uri: AnyUrl | str) -> AnyUrl:
        if isinstance(uri, str):
            # AnyUrl doesn't support triple-slashes, but files do ("file:///absolute/path")
            if uri.startswith("file://"):
                return FileUrl(uri)
            return AnyUrl(uri)
        return uri

    @field_validator("name", mode="before")
    @classmethod
    def set_default_name(cls, name: str | None, info: ValidationInfo) -> str:
        """Set default name from URI if not provided."""
        if name:
            return name
        if uri := info.data.get("uri"):
            return str(uri)
        raise ValueError("Either name or uri must be provided")

    @abc.abstractmethod
    async def read(self) -> Union[str, bytes]:
        """Read the resource content."""
        pass
