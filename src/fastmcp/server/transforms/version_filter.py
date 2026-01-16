"""Version filter transform for filtering components by version range."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from fastmcp.server.transforms import (
    GetPromptNext,
    GetPromptVersionsNext,
    GetResourceNext,
    GetResourceTemplateNext,
    GetResourceTemplateVersionsNext,
    GetResourceVersionsNext,
    GetToolNext,
    GetToolVersionsNext,
    ListPromptsNext,
    ListResourcesNext,
    ListResourceTemplatesNext,
    ListToolsNext,
    Transform,
)
from fastmcp.utilities.versions import VersionKey, parse_version_key

if TYPE_CHECKING:
    from fastmcp.prompts.prompt import Prompt
    from fastmcp.resources.resource import Resource
    from fastmcp.resources.template import ResourceTemplate
    from fastmcp.tools.tool import Tool


class VersionFilter(Transform):
    """Filters components by version range.

    When applied to a provider or server, only components within the version
    range are visible. Within that filtered set, the highest version of each
    component is exposed to clients (standard deduplication behavior).

    Parameters mirror comparison operators for clarity:

        # Versions < 3.0 (v1 and v2)
        server.add_transform(VersionFilter(version_lt="3.0"))

        # Versions >= 2.0 and < 3.0 (only v2.x)
        server.add_transform(VersionFilter(version_gte="2.0", version_lt="3.0"))

    Works with any version string - PEP 440 (1.0, 2.0) or dates (2025-01-01).

    Args:
        version_gte: Versions >= this value pass through.
        version_lt: Versions < this value pass through.
    """

    def __init__(
        self,
        *,
        version_gte: str | None = None,
        version_lt: str | None = None,
    ) -> None:
        if version_gte is None and version_lt is None:
            raise ValueError(
                "At least one of version_gte or version_lt must be specified"
            )
        self.version_gte = version_gte
        self.version_lt = version_lt
        self._gte_key: VersionKey | None = (
            parse_version_key(version_gte) if version_gte else None
        )
        self._lt_key: VersionKey | None = (
            parse_version_key(version_lt) if version_lt else None
        )

    def __repr__(self) -> str:
        parts = []
        if self.version_gte:
            parts.append(f"version_gte={self.version_gte!r}")
        if self.version_lt:
            parts.append(f"version_lt={self.version_lt!r}")
        return f"VersionFilter({', '.join(parts)})"

    def _in_range(self, version: str | None) -> bool:
        """Check if version passes the filter."""
        if version is None:
            # Unversioned always passes
            return True
        key = parse_version_key(version)
        if self._gte_key and key < self._gte_key:
            return False
        # key >= lt_key means out of range
        return not (self._lt_key and not key < self._lt_key)

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    async def list_tools(self, call_next: ListToolsNext) -> Sequence[Tool]:
        tools = await call_next()
        return [t for t in tools if self._in_range(t.version)]

    async def get_tool(self, name: str, call_next: GetToolNext) -> Tool | None:
        tool = await call_next(name)
        if tool and not self._in_range(tool.version):
            return None
        return tool

    async def get_tool_versions(
        self, name: str, call_next: GetToolVersionsNext
    ) -> Sequence[Tool]:
        tools = await call_next(name)
        return [t for t in tools if self._in_range(t.version)]

    # -------------------------------------------------------------------------
    # Resources
    # -------------------------------------------------------------------------

    async def list_resources(self, call_next: ListResourcesNext) -> Sequence[Resource]:
        resources = await call_next()
        return [r for r in resources if self._in_range(r.version)]

    async def get_resource(
        self, uri: str, call_next: GetResourceNext
    ) -> Resource | None:
        resource = await call_next(uri)
        if resource and not self._in_range(resource.version):
            return None
        return resource

    async def get_resource_versions(
        self, uri: str, call_next: GetResourceVersionsNext
    ) -> Sequence[Resource]:
        resources = await call_next(uri)
        return [r for r in resources if self._in_range(r.version)]

    # -------------------------------------------------------------------------
    # Resource Templates
    # -------------------------------------------------------------------------

    async def list_resource_templates(
        self, call_next: ListResourceTemplatesNext
    ) -> Sequence[ResourceTemplate]:
        templates = await call_next()
        return [t for t in templates if self._in_range(t.version)]

    async def get_resource_template(
        self, uri: str, call_next: GetResourceTemplateNext
    ) -> ResourceTemplate | None:
        template = await call_next(uri)
        if template and not self._in_range(template.version):
            return None
        return template

    async def get_resource_template_versions(
        self, uri_template: str, call_next: GetResourceTemplateVersionsNext
    ) -> Sequence[ResourceTemplate]:
        templates = await call_next(uri_template)
        return [t for t in templates if self._in_range(t.version)]

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------

    async def list_prompts(self, call_next: ListPromptsNext) -> Sequence[Prompt]:
        prompts = await call_next()
        return [p for p in prompts if self._in_range(p.version)]

    async def get_prompt(self, name: str, call_next: GetPromptNext) -> Prompt | None:
        prompt = await call_next(name)
        if prompt and not self._in_range(prompt.version):
            return None
        return prompt

    async def get_prompt_versions(
        self, name: str, call_next: GetPromptVersionsNext
    ) -> Sequence[Prompt]:
        prompts = await call_next(name)
        return [p for p in prompts if self._in_range(p.version)]
