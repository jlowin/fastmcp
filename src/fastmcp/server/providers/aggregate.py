"""AggregateProvider for combining multiple providers into one.

This module provides `AggregateProvider` which presents multiple providers
as a single unified provider. Used internally by FastMCP for applying
server-level transforms across all providers.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager

from fastmcp.prompts.prompt import Prompt
from fastmcp.resources.resource import Resource
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.providers.base import Provider
from fastmcp.tools.tool import Tool
from fastmcp.utilities.components import FastMCPComponent


class AggregateProvider(Provider):
    """Presents multiple providers as a single provider.

    Components are aggregated from all providers. For get_* operations,
    providers are queried in order and the first non-None result is returned.

    Errors propagate to the caller - this is an invisible helper and does not
    handle errors itself. The caller (typically FastMCP) decides error policy.
    """

    def __init__(self, providers: Sequence[Provider]) -> None:
        """Initialize with a sequence of providers.

        Args:
            providers: The providers to aggregate. Queried in order for lookups.
        """
        super().__init__()
        self._providers = list(providers)

    def __repr__(self) -> str:
        return f"AggregateProvider(providers={self._providers!r})"

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    async def list_tools(self) -> Sequence[Tool]:
        """List all tools from all providers."""
        results = await asyncio.gather(*[p.list_tools() for p in self._providers])
        return [tool for tools in results for tool in tools]

    async def get_tool(self, name: str) -> Tool | None:
        """Get tool by name from first provider that has it."""
        for provider in self._providers:
            tool = await provider.get_tool(name)
            if tool is not None:
                return tool
        return None

    # -------------------------------------------------------------------------
    # Resources
    # -------------------------------------------------------------------------

    async def list_resources(self) -> Sequence[Resource]:
        """List all resources from all providers."""
        results = await asyncio.gather(*[p.list_resources() for p in self._providers])
        return [resource for resources in results for resource in resources]

    async def get_resource(self, uri: str) -> Resource | None:
        """Get resource by URI from first provider that has it."""
        for provider in self._providers:
            resource = await provider.get_resource(uri)
            if resource is not None:
                return resource
        return None

    # -------------------------------------------------------------------------
    # Resource Templates
    # -------------------------------------------------------------------------

    async def list_resource_templates(self) -> Sequence[ResourceTemplate]:
        """List all resource templates from all providers."""
        results = await asyncio.gather(
            *[p.list_resource_templates() for p in self._providers]
        )
        return [template for templates in results for template in templates]

    async def get_resource_template(self, uri: str) -> ResourceTemplate | None:
        """Get resource template by URI from first provider that has it."""
        for provider in self._providers:
            template = await provider.get_resource_template(uri)
            if template is not None:
                return template
        return None

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------

    async def list_prompts(self) -> Sequence[Prompt]:
        """List all prompts from all providers."""
        results = await asyncio.gather(*[p.list_prompts() for p in self._providers])
        return [prompt for prompts in results for prompt in prompts]

    async def get_prompt(self, name: str) -> Prompt | None:
        """Get prompt by name from first provider that has it."""
        for provider in self._providers:
            prompt = await provider.get_prompt(name)
            if prompt is not None:
                return prompt
        return None

    # -------------------------------------------------------------------------
    # Components
    # -------------------------------------------------------------------------

    async def get_component(
        self, key: str
    ) -> Tool | Resource | ResourceTemplate | Prompt | None:
        """Get component by key from first provider that has it."""
        for provider in self._providers:
            component = await provider.get_component(key)
            if component is not None:
                return component
        return None

    # -------------------------------------------------------------------------
    # Tasks
    # -------------------------------------------------------------------------

    async def get_tasks(self) -> Sequence[FastMCPComponent]:
        """Get all task-eligible components from all providers."""
        results = await asyncio.gather(*[p.get_tasks() for p in self._providers])
        return [component for components in results for component in components]

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        """Combine lifespans of all providers."""
        async with AsyncExitStack() as stack:
            for provider in self._providers:
                await stack.enter_async_context(provider.lifespan())
            yield

