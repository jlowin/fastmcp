"""Transform system for component transformations.

Transforms modify components (tools, resources, prompts). List operations use a pure
function pattern where transforms receive sequences and return transformed sequences.
Get operations use a middleware pattern with `call_next` to chain lookups.

Unlike middleware (which operates on requests), transforms are observable by the
system for task registration, tag filtering, and component introspection.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.transforms import Namespace

    server = FastMCP("Server")
    mount = server.mount(other_server)
    mount.add_transform(Namespace("api"))  # Tools become api_toolname
    ```
"""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from typing import TYPE_CHECKING, Protocol

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)
from fastmcp.utilities.versions import VersionSpec

if TYPE_CHECKING:
    from fastmcp.prompts.base import Prompt
    from fastmcp.resources.base import Resource
    from fastmcp.resources.template import ResourceTemplate
    from fastmcp.server.transforms.namespace import Namespace as Namespace
    from fastmcp.server.transforms.prompts_as_tools import (
        PromptsAsTools as PromptsAsTools,
    )
    from fastmcp.server.transforms.resources_as_tools import (
        ResourcesAsTools as ResourcesAsTools,
    )
    from fastmcp.server.transforms.tool_transform import (
        ToolTransform as ToolTransform,
    )
    from fastmcp.server.transforms.version_filter import (
        VersionFilter as VersionFilter,
    )
    from fastmcp.server.transforms.visibility import Visibility as Visibility
    from fastmcp.server.transforms.visibility import is_enabled as is_enabled
    from fastmcp.tools.base import Tool


# Get methods use Protocol to express keyword-only version parameter
class GetToolNext(Protocol):
    """Protocol for get_tool call_next functions."""

    def __call__(
        self, name: str, *, version: VersionSpec | None = None
    ) -> Awaitable[Tool | None]: ...


class GetResourceNext(Protocol):
    """Protocol for get_resource call_next functions."""

    def __call__(
        self, uri: str, *, version: VersionSpec | None = None
    ) -> Awaitable[Resource | None]: ...


class GetResourceTemplateNext(Protocol):
    """Protocol for get_resource_template call_next functions."""

    def __call__(
        self, uri: str, *, version: VersionSpec | None = None
    ) -> Awaitable[ResourceTemplate | None]: ...


class GetPromptNext(Protocol):
    """Protocol for get_prompt call_next functions."""

    def __call__(
        self, name: str, *, version: VersionSpec | None = None
    ) -> Awaitable[Prompt | None]: ...


class Transform:
    """Base class for component transformations.

    List operations use a pure function pattern: transforms receive sequences
    and return transformed sequences. Get operations use a middleware pattern
    with `call_next` to chain lookups.

    Example:
        ```python
        class MyTransform(Transform):
            async def list_tools(self, tools):
                return [transform(t) for t in tools]  # Transform sequence

            async def get_tool(self, name, call_next, *, version=None):
                original = self.reverse_name(name)  # Map to original name
                tool = await call_next(original, version=version)  # Get from downstream
                return transform(tool) if tool else None
        ```
    """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    async def list_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        """List tools with transformation applied.

        Args:
            tools: Sequence of tools to transform.

        Returns:
            Transformed sequence of tools.
        """
        return tools

    async def get_tool(
        self, name: str, call_next: GetToolNext, *, version: VersionSpec | None = None
    ) -> Tool | None:
        """Get a tool by name.

        Args:
            name: The requested tool name (may be transformed).
            call_next: Callable to get tool from downstream.
            version: Optional version filter to apply.

        Returns:
            The tool if found, None otherwise.
        """
        return await call_next(name, version=version)

    # -------------------------------------------------------------------------
    # Resources
    # -------------------------------------------------------------------------

    async def list_resources(self, resources: Sequence[Resource]) -> Sequence[Resource]:
        """List resources with transformation applied.

        Args:
            resources: Sequence of resources to transform.

        Returns:
            Transformed sequence of resources.
        """
        return resources

    async def get_resource(
        self,
        uri: str,
        call_next: GetResourceNext,
        *,
        version: VersionSpec | None = None,
    ) -> Resource | None:
        """Get a resource by URI.

        Args:
            uri: The requested resource URI (may be transformed).
            call_next: Callable to get resource from downstream.
            version: Optional version filter to apply.

        Returns:
            The resource if found, None otherwise.
        """
        return await call_next(uri, version=version)

    # -------------------------------------------------------------------------
    # Resource Templates
    # -------------------------------------------------------------------------

    async def list_resource_templates(
        self, templates: Sequence[ResourceTemplate]
    ) -> Sequence[ResourceTemplate]:
        """List resource templates with transformation applied.

        Args:
            templates: Sequence of resource templates to transform.

        Returns:
            Transformed sequence of resource templates.
        """
        return templates

    async def get_resource_template(
        self,
        uri: str,
        call_next: GetResourceTemplateNext,
        *,
        version: VersionSpec | None = None,
    ) -> ResourceTemplate | None:
        """Get a resource template by URI.

        Args:
            uri: The requested template URI (may be transformed).
            call_next: Callable to get template from downstream.
            version: Optional version filter to apply.

        Returns:
            The resource template if found, None otherwise.
        """
        return await call_next(uri, version=version)

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------

    async def list_prompts(self, prompts: Sequence[Prompt]) -> Sequence[Prompt]:
        """List prompts with transformation applied.

        Args:
            prompts: Sequence of prompts to transform.

        Returns:
            Transformed sequence of prompts.
        """
        return prompts

    async def get_prompt(
        self, name: str, call_next: GetPromptNext, *, version: VersionSpec | None = None
    ) -> Prompt | None:
        """Get a prompt by name.

        Args:
            name: The requested prompt name (may be transformed).
            call_next: Callable to get prompt from downstream.
            version: Optional version filter to apply.

        Returns:
            The prompt if found, None otherwise.
        """
        return await call_next(name, version=version)


__all__ = [
    "Namespace",
    "PromptsAsTools",
    "ResourcesAsTools",
    "ToolTransform",
    "Transform",
    "VersionFilter",
    "VersionSpec",
    "Visibility",
    "is_enabled",
]

_LAZY_IMPORTS = {
    "Namespace": ("fastmcp.server.transforms.namespace", "Namespace"),
    "PromptsAsTools": (
        "fastmcp.server.transforms.prompts_as_tools",
        "PromptsAsTools",
    ),
    "ResourcesAsTools": (
        "fastmcp.server.transforms.resources_as_tools",
        "ResourcesAsTools",
    ),
    "ToolTransform": (
        "fastmcp.server.transforms.tool_transform",
        "ToolTransform",
    ),
    "VersionFilter": (
        "fastmcp.server.transforms.version_filter",
        "VersionFilter",
    ),
    "Visibility": ("fastmcp.server.transforms.visibility", "Visibility"),
    "is_enabled": ("fastmcp.server.transforms.visibility", "is_enabled"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
