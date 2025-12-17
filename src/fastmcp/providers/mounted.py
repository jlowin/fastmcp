"""MountedProvider for wrapping mounted FastMCP servers.

This module provides the `MountedProvider` class that enables mounting
one FastMCP server onto another, exposing the mounted server's tools,
resources, and prompts through the parent server with optional prefixing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import NotFoundError
from fastmcp.prompts.prompt import Prompt, PromptResult
from fastmcp.providers.base import Components, Provider
from fastmcp.resources.resource import Resource, ResourceContent
from fastmcp.resources.template import ResourceTemplate
from fastmcp.tools.tool import Tool, ToolResult

if TYPE_CHECKING:
    from fastmcp.server.server import FastMCP


class MountedProvider(Provider):
    """Provider that wraps a mounted FastMCP server.

    This provider enables mounting one FastMCP server onto another, exposing
    the mounted server's tools, resources, and prompts through the parent
    server with optional prefixing.

    The key benefit is that execution methods (`call_tool`, `read_resource`,
    `render_prompt`) invoke the mounted server's middleware chain, enabling
    full participation in the provider abstraction.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.providers import MountedProvider

        main = FastMCP("Main")
        sub = FastMCP("Sub")

        @sub.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        # Mount with prefix - tool accessible as "sub_greet"
        main.add_provider(MountedProvider(sub, prefix="sub"))
        ```

    Note:
        Normally you would use `FastMCP.mount()` which handles proxy conversion
        and creates the MountedProvider internally.
    """

    def __init__(
        self,
        server: FastMCP[Any],
        prefix: str | None = None,
        tool_names: dict[str, str] | None = None,
    ):
        """Initialize a MountedProvider.

        Args:
            server: The FastMCP server to mount.
            prefix: Optional prefix for tool/prompt names and resource URIs.
                Tools and prompts use underscore separator: "prefix_name".
                Resources use path-style: "protocol://prefix/path".
            tool_names: Optional mapping of original tool names to custom names.
                Overrides the default prefixed names for specific tools.
        """
        super().__init__()
        self.server = server
        self.prefix = prefix
        self.tool_names = tool_names or {}
        self._reverse_tool_names = {v: k for k, v in self.tool_names.items()}

    # -------------------------------------------------------------------------
    # Helper methods for prefix handling
    # -------------------------------------------------------------------------

    def _add_tool_prefix(self, name: str) -> str:
        """Add prefix to a tool or prompt name."""
        if self.prefix:
            return f"{self.prefix}_{name}"
        return name

    def _strip_tool_prefix(self, name: str) -> str | None:
        """Strip prefix from a tool or prompt name.

        Returns:
            The unprefixed name if the name matches this provider's pattern,
            or None if it doesn't match (indicating another provider should handle it).
        """
        # Check for tool_names override first
        if name in self._reverse_tool_names:
            return self._reverse_tool_names[name]

        # Check prefix pattern
        if self.prefix:
            expected_prefix = f"{self.prefix}_"
            if name.startswith(expected_prefix):
                return name[len(expected_prefix) :]
            return None  # Doesn't match this provider

        # No prefix means we always match
        return name

    def _add_resource_prefix(self, uri: str) -> str:
        """Add prefix to a resource URI."""
        if not self.prefix:
            return uri
        # Import here to avoid circular dependency
        from fastmcp.server.server import add_resource_prefix

        return add_resource_prefix(uri, self.prefix)

    def _strip_resource_prefix(self, uri: str) -> str | None:
        """Strip prefix from a resource URI.

        Returns:
            The unprefixed URI if it matches this provider's pattern,
            or None if it doesn't match.
        """
        if not self.prefix:
            return uri
        # Import here to avoid circular dependency
        from fastmcp.server.server import has_resource_prefix, remove_resource_prefix

        if not has_resource_prefix(uri, self.prefix):
            return None
        return remove_resource_prefix(uri, self.prefix)

    # -------------------------------------------------------------------------
    # Prefix helper methods for components
    # -------------------------------------------------------------------------

    def _prefix_tool(self, tool: Tool) -> Tool:
        """Apply prefix to a tool."""
        if self.tool_names and tool.name in self.tool_names:
            new_key = self.tool_names[tool.name]
        else:
            new_key = self._add_tool_prefix(tool.key)
        return tool.model_copy(key=new_key) if new_key != tool.key else tool

    def _prefix_resource(self, resource: Resource) -> Resource:
        """Apply prefix to a resource."""
        new_key = self._add_resource_prefix(resource.key)
        update: dict[str, Any] = {}
        if self.prefix and resource.name:
            update["name"] = f"{self.prefix}_{resource.name}"
        if new_key != resource.key or update:
            return resource.model_copy(key=new_key, update=update)
        return resource

    def _prefix_template(self, template: ResourceTemplate) -> ResourceTemplate:
        """Apply prefix to a resource template."""
        new_key = self._add_resource_prefix(template.key)
        update: dict[str, Any] = {}
        if self.prefix and template.name:
            update["name"] = f"{self.prefix}_{template.name}"
        if self.prefix and template.uri_template:
            update["uri_template"] = self._add_resource_prefix(template.uri_template)
        if new_key != template.key or update:
            return template.model_copy(key=new_key, update=update)
        return template

    def _prefix_prompt(self, prompt: Prompt) -> Prompt:
        """Apply prefix to a prompt."""
        new_key = self._add_tool_prefix(prompt.key)
        return prompt.model_copy(key=new_key) if new_key != prompt.key else prompt

    # -------------------------------------------------------------------------
    # Tool methods
    # -------------------------------------------------------------------------

    async def list_tools(self) -> Sequence[Tool]:
        """List all tools from the mounted server with prefixes applied."""
        tools = await self.server._list_tools_middleware()
        return [self._prefix_tool(tool) for tool in tools]

    async def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name, checking if it matches our prefix pattern."""
        unprefixed = self._strip_tool_prefix(name)
        if unprefixed is None:
            return None  # Doesn't match this provider

        try:
            tool = await self.server.get_tool(unprefixed)
            # Return with prefixed key for parent's filter checking
            prefixed_key = name  # The name we received is already the prefixed form
            if tool.key != prefixed_key:
                tool = tool.model_copy(key=prefixed_key)
            return tool
        except NotFoundError:
            return None

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> ToolResult | None:
        """Execute a tool through the mounted server's middleware chain."""
        unprefixed = self._strip_tool_prefix(name)
        if unprefixed is None:
            return None  # Doesn't match this provider

        return await self.server._call_tool_middleware(unprefixed, arguments)

    # -------------------------------------------------------------------------
    # Resource methods
    # -------------------------------------------------------------------------

    async def list_resources(self) -> Sequence[Resource]:
        """List all resources from the mounted server with prefixes applied."""
        resources = await self.server._list_resources_middleware()
        return [self._prefix_resource(resource) for resource in resources]

    async def get_resource(self, uri: str) -> Resource | None:
        """Get a concrete resource by URI, checking if it matches our prefix pattern.

        This only returns concrete resources, not resources created from templates.
        For templates, use get_resource_template() instead.
        """
        unprefixed = self._strip_resource_prefix(uri)
        if unprefixed is None:
            return None  # Doesn't match this provider

        # Only check concrete resources (not templates that match the URI)
        # This preserves the original template for task execution
        resources = await self.server.get_resources()
        if unprefixed not in resources:
            return None
        resource = resources[unprefixed]

        # Return with prefixed key for parent's filter checking
        return self._prefix_resource(resource)

    async def read_resource(self, uri: str) -> ResourceContent | None:
        """Read a resource through the mounted server's middleware chain."""
        unprefixed = self._strip_resource_prefix(uri)
        if unprefixed is None:
            return None  # Doesn't match this provider

        try:
            contents = await self.server._read_resource_middleware(unprefixed)
            return contents[0] if contents else None
        except NotFoundError:
            return None

    # -------------------------------------------------------------------------
    # Resource template methods
    # -------------------------------------------------------------------------

    async def list_resource_templates(self) -> Sequence[ResourceTemplate]:
        """List all resource templates from the mounted server with prefixes applied."""
        templates = await self.server._list_resource_templates_middleware()
        return [self._prefix_template(template) for template in templates]

    async def get_resource_template(self, uri: str) -> ResourceTemplate | None:
        """Get a resource template that matches the given URI."""
        # For templates, we need to check if any template matches the prefixed URI
        unprefixed = self._strip_resource_prefix(uri)
        if unprefixed is None:
            return None

        # Use middleware to include templates from nested mounted providers
        templates = await self.server._list_resource_templates_middleware()
        for template in templates:
            if template.matches(unprefixed) is not None:
                return self._prefix_template(template)
        return None

    async def read_resource_template(self, uri: str) -> ResourceContent | None:
        """Read a resource via a matching template through the mounted server."""
        # This is handled by read_resource since the server's middleware handles templates
        return await self.read_resource(uri)

    # -------------------------------------------------------------------------
    # Prompt methods
    # -------------------------------------------------------------------------

    async def list_prompts(self) -> Sequence[Prompt]:
        """List all prompts from the mounted server with prefixes applied."""
        prompts = await self.server._list_prompts_middleware()
        return [self._prefix_prompt(prompt) for prompt in prompts]

    async def get_prompt(self, name: str) -> Prompt | None:
        """Get a prompt by name, checking if it matches our prefix pattern."""
        unprefixed = self._strip_tool_prefix(name)
        if unprefixed is None:
            return None  # Doesn't match this provider

        try:
            prompt = await self.server.get_prompt(unprefixed)
            # Return with prefixed key for parent's filter checking
            prefixed_key = name
            if prompt.key != prefixed_key:
                prompt = prompt.model_copy(key=prefixed_key)
            return prompt
        except NotFoundError:
            return None

    async def render_prompt(
        self, name: str, arguments: dict[str, Any] | None
    ) -> PromptResult | None:
        """Render a prompt through the mounted server's middleware chain."""
        unprefixed = self._strip_tool_prefix(name)
        if unprefixed is None:
            return None  # Doesn't match this provider

        return await self.server._get_prompt_content_middleware(unprefixed, arguments)

    # -------------------------------------------------------------------------
    # Task registration
    # -------------------------------------------------------------------------

    async def get_tasks(self) -> Components:
        """Return task-eligible components, bypassing middleware and applying prefixes.

        This override accesses the wrapped server's managers directly to avoid
        triggering middleware during registration. It also recursively collects
        tasks from nested providers.
        """
        from fastmcp.prompts.prompt import FunctionPrompt
        from fastmcp.resources.resource import FunctionResource
        from fastmcp.resources.template import FunctionResourceTemplate
        from fastmcp.tools.tool import FunctionTool

        tools: list[Tool] = []
        resources: list[Resource] = []
        templates: list[ResourceTemplate] = []
        prompts: list[Prompt] = []

        # Direct manager access (bypasses middleware)
        for tool in self.server._tool_manager._tools.values():
            if isinstance(tool, FunctionTool) and tool.task_config.mode != "forbidden":
                tools.append(self._prefix_tool(tool))

        for resource in self.server._resource_manager._resources.values():
            if (
                isinstance(resource, FunctionResource)
                and resource.task_config.mode != "forbidden"
            ):
                resources.append(self._prefix_resource(resource))

        for template in self.server._resource_manager._templates.values():
            if (
                isinstance(template, FunctionResourceTemplate)
                and template.task_config.mode != "forbidden"
            ):
                templates.append(self._prefix_template(template))

        for prompt in self.server._prompt_manager._prompts.values():
            if (
                isinstance(prompt, FunctionPrompt)
                and prompt.task_config.mode != "forbidden"
            ):
                prompts.append(self._prefix_prompt(prompt))

        # Recursively get tasks from nested providers and apply our prefix
        for provider in self.server._providers:
            nested = await provider.get_tasks()
            tools.extend(self._prefix_tool(t) for t in nested.tools)
            resources.extend(self._prefix_resource(r) for r in nested.resources)
            templates.extend(self._prefix_template(t) for t in nested.templates)
            prompts.extend(self._prefix_prompt(p) for p in nested.prompts)

        return Components(
            tools=tools, resources=resources, templates=templates, prompts=prompts
        )

    # -------------------------------------------------------------------------
    # Lifecycle methods
    # -------------------------------------------------------------------------

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        """Start the mounted server's user lifespan.

        This starts only the wrapped server's user-defined lifespan, NOT its
        full _lifespan_manager() (which includes Docket). The parent server's
        Docket handles all background tasks.
        """
        # Start the wrapped server's user lifespan only
        # We pass the server instance to the user's lifespan function
        async with self.server._lifespan(self.server):
            yield
