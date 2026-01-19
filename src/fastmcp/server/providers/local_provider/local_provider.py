"""LocalProvider for locally-defined MCP components.

This module provides the `LocalProvider` class that manages tools, resources,
templates, and prompts registered via decorators or direct methods.

LocalProvider can be used standalone and attached to multiple servers:

```python
from fastmcp.server.providers import LocalProvider

# Create a reusable provider with tools
provider = LocalProvider()

@provider.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"

# Attach to any server
from fastmcp import FastMCP
server1 = FastMCP("Server1", providers=[provider])
server2 = FastMCP("Server2", providers=[provider])
```
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from fastmcp.prompts.prompt import Prompt
from fastmcp.resources.resource import Resource
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.providers.base import Provider
from fastmcp.tools.tool import Tool
from fastmcp.utilities.components import FastMCPComponent
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.versions import VersionSpec, version_sort_key

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

DuplicateBehavior = Literal["error", "warn", "replace", "ignore"]

_C = TypeVar("_C", bound=FastMCPComponent)


class LocalProvider(Provider):
    """Provider for locally-defined components.

    Supports decorator-based registration (`@provider.tool`, `@provider.resource`,
    `@provider.prompt`) and direct object registration methods.

    When used standalone, LocalProvider uses default settings. When attached
    to a FastMCP server via the server's decorators, server-level settings
    like `_tool_serializer` and `_support_tasks_by_default` are injected.

    Example:
        ```python
        from fastmcp.server.providers import LocalProvider

        # Standalone usage
        provider = LocalProvider()

        @provider.tool
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        @provider.resource("data://config")
        def get_config() -> str:
            return '{"setting": "value"}'

        @provider.prompt
        def analyze(topic: str) -> list:
            return [{"role": "user", "content": f"Analyze: {topic}"}]

        # Attach to server(s)
        from fastmcp import FastMCP
        server = FastMCP("MyServer", providers=[provider])
        ```
    """

    def __init__(
        self,
        on_duplicate: DuplicateBehavior = "error",
    ) -> None:
        """Initialize a LocalProvider with empty storage.

        Args:
            on_duplicate: Behavior when adding a component that already exists:
                - "error": Raise ValueError
                - "warn": Log warning and replace
                - "replace": Silently replace
                - "ignore": Keep existing, return it
        """
        super().__init__()
        self._on_duplicate = on_duplicate
        # Unified component storage - keyed by prefixed key (e.g., "tool:name", "resource:uri")
        self._components: dict[str, FastMCPComponent] = {}

    # =========================================================================
    # Storage methods
    # =========================================================================

    def _get_component_identity(self, component: FastMCPComponent) -> tuple[type, str]:
        """Get the identity (type, name/uri) for a component.

        Returns:
            A tuple of (component_type, logical_name) where logical_name is
            the name for tools/prompts or URI for resources/templates.
        """
        if isinstance(component, Tool):
            return (Tool, component.name)
        elif isinstance(component, ResourceTemplate):
            return (ResourceTemplate, component.uri_template)
        elif isinstance(component, Resource):
            return (Resource, str(component.uri))
        elif isinstance(component, Prompt):
            return (Prompt, component.name)
        else:
            # Fall back to key without version suffix
            key = component.key
            base_key = key.rsplit("@", 1)[0] if "@" in key else key
            return (type(component), base_key)

    def _check_version_mixing(self, component: _C) -> None:
        """Check that versioned and unversioned components aren't mixed.

        LocalProvider enforces a simple rule: for any given name/URI, all
        registered components must either be versioned or unversioned, not both.
        This prevents confusing situations where unversioned components can't
        be filtered out by version filters.

        Args:
            component: The component being added.

        Raises:
            ValueError: If adding would mix versioned and unversioned components.
        """
        comp_type, logical_name = self._get_component_identity(component)
        is_versioned = component.version is not None

        # Check all existing components of the same type and logical name
        for existing in self._components.values():
            if not isinstance(existing, comp_type):
                continue

            _, existing_name = self._get_component_identity(existing)
            if existing_name != logical_name:
                continue

            existing_versioned = existing.version is not None
            if is_versioned != existing_versioned:
                type_name = comp_type.__name__.lower()
                if is_versioned:
                    raise ValueError(
                        f"Cannot add versioned {type_name} {logical_name!r} "
                        f"(version={component.version!r}): an unversioned "
                        f"{type_name} with this name already exists. "
                        f"Either version all components or none."
                    )
                else:
                    raise ValueError(
                        f"Cannot add unversioned {type_name} {logical_name!r}: "
                        f"versioned {type_name}s with this name already exist "
                        f"(e.g., version={existing.version!r}). "
                        f"Either version all components or none."
                    )

    def _add_component(self, component: _C) -> _C:
        """Add a component to unified storage.

        Args:
            component: The component to add.

        Returns:
            The component that was added (or existing if on_duplicate="ignore").
        """
        existing = self._components.get(component.key)
        if existing:
            if self._on_duplicate == "error":
                raise ValueError(f"Component already exists: {component.key}")
            elif self._on_duplicate == "warn":
                logger.warning(f"Component already exists: {component.key}")
            elif self._on_duplicate == "ignore":
                return existing  # type: ignore[return-value]
            # "replace" and "warn" fall through to add

        # Check for versioned/unversioned mixing before adding
        self._check_version_mixing(component)

        self._components[component.key] = component
        return component

    def _remove_component(self, key: str) -> None:
        """Remove a component from unified storage.

        Args:
            key: The prefixed key of the component.

        Raises:
            KeyError: If the component is not found.
        """
        component = self._components.get(key)
        if component is None:
            raise KeyError(f"Component {key!r} not found")

        del self._components[key]

    def _get_component(self, key: str) -> FastMCPComponent | None:
        """Get a component by its prefixed key.

        Args:
            key: The prefixed key (e.g., "tool:name", "resource:uri").

        Returns:
            The component, or None if not found.
        """
        return self._components.get(key)

    def add_tool(self, tool: Tool | Callable[..., Any]) -> Tool:
        """Add a tool to this provider's storage.

        Accepts either a Tool object or a decorated function with __fastmcp__ metadata.
        """
        if isinstance(tool, Tool):
            self._add_component(tool)
            return tool

        # Handle decorated function with metadata
        from fastmcp.decorators import get_fastmcp_meta
        from fastmcp.tools.function_tool import ToolMeta

        meta = get_fastmcp_meta(tool)
        if meta is not None and isinstance(meta, ToolMeta):
            resolved_task = meta.task if meta.task is not None else False
            enabled = meta.enabled
            tool_obj = Tool.from_function(
                tool,
                name=meta.name,
                version=meta.version,
                title=meta.title,
                description=meta.description,
                icons=meta.icons,
                tags=meta.tags,
                output_schema=meta.output_schema,
                annotations=meta.annotations,
                meta=meta.meta,
                task=resolved_task,
                exclude_args=meta.exclude_args,
                serializer=meta.serializer,
                timeout=meta.timeout,
                auth=meta.auth,
            )
        else:
            tool_obj = Tool.from_function(tool)
            enabled = True

        self._add_component(tool_obj)
        if not enabled:
            self.disable(keys={tool_obj.key})
        return tool_obj

    def remove_tool(self, name: str, version: str | None = None) -> None:
        """Remove tool(s) from this provider's storage.

        Args:
            name: The tool name.
            version: If None, removes ALL versions. If specified, removes only that version.

        Raises:
            KeyError: If no matching tool is found.
        """
        if version is None:
            # Remove all versions
            keys_to_remove = [
                k
                for k, c in self._components.items()
                if isinstance(c, Tool) and c.name == name
            ]
            if not keys_to_remove:
                raise KeyError(f"Tool {name!r} not found")
            for key in keys_to_remove:
                self._remove_component(key)
        else:
            # Remove specific version - key format is "tool:name@version"
            key = f"{Tool.make_key(name)}@{version}"
            if key not in self._components:
                raise KeyError(f"Tool {name!r} version {version!r} not found")
            self._remove_component(key)

    def add_resource(
        self, resource: Resource | ResourceTemplate | Callable[..., Any]
    ) -> Resource | ResourceTemplate:
        """Add a resource to this provider's storage.

        Accepts either a Resource/ResourceTemplate object or a decorated function with __fastmcp__ metadata.
        """
        if isinstance(resource, (Resource, ResourceTemplate)):
            self._add_component(resource)
            return resource

        # Handle decorated function with metadata
        from fastmcp.decorators import get_fastmcp_meta
        from fastmcp.resources.function_resource import ResourceMeta
        from fastmcp.server.dependencies import without_injected_parameters

        meta = get_fastmcp_meta(resource)
        if meta is not None and isinstance(meta, ResourceMeta):
            resolved_task = meta.task if meta.task is not None else False
            enabled = meta.enabled
            has_uri_params = "{" in meta.uri and "}" in meta.uri
            wrapper_fn = without_injected_parameters(resource)
            has_func_params = bool(inspect.signature(wrapper_fn).parameters)

            if has_uri_params or has_func_params:
                resource_obj = ResourceTemplate.from_function(
                    fn=resource,
                    uri_template=meta.uri,
                    name=meta.name,
                    version=meta.version,
                    title=meta.title,
                    description=meta.description,
                    icons=meta.icons,
                    mime_type=meta.mime_type,
                    tags=meta.tags,
                    annotations=meta.annotations,
                    meta=meta.meta,
                    task=resolved_task,
                    auth=meta.auth,
                )
            else:
                resource_obj = Resource.from_function(
                    fn=resource,
                    uri=meta.uri,
                    name=meta.name,
                    version=meta.version,
                    title=meta.title,
                    description=meta.description,
                    icons=meta.icons,
                    mime_type=meta.mime_type,
                    tags=meta.tags,
                    annotations=meta.annotations,
                    meta=meta.meta,
                    task=resolved_task,
                    auth=meta.auth,
                )
        else:
            raise TypeError(
                f"Expected Resource, ResourceTemplate, or @resource-decorated function, got {type(resource).__name__}. "
                "Use @resource('uri') decorator or pass a Resource/ResourceTemplate instance."
            )

        self._add_component(resource_obj)
        if not enabled:
            self.disable(keys={resource_obj.key})
        return resource_obj

    def remove_resource(self, uri: str, version: str | None = None) -> None:
        """Remove resource(s) from this provider's storage.

        Args:
            uri: The resource URI.
            version: If None, removes ALL versions. If specified, removes only that version.

        Raises:
            KeyError: If no matching resource is found.
        """
        if version is None:
            # Remove all versions
            keys_to_remove = [
                k
                for k, c in self._components.items()
                if isinstance(c, Resource) and str(c.uri) == uri
            ]
            if not keys_to_remove:
                raise KeyError(f"Resource {uri!r} not found")
            for key in keys_to_remove:
                self._remove_component(key)
        else:
            # Remove specific version
            key = f"{Resource.make_key(uri)}@{version}"
            if key not in self._components:
                raise KeyError(f"Resource {uri!r} version {version!r} not found")
            self._remove_component(key)

    def add_template(self, template: ResourceTemplate) -> ResourceTemplate:
        """Add a resource template to this provider's storage."""
        return self._add_component(template)

    def remove_template(self, uri_template: str, version: str | None = None) -> None:
        """Remove resource template(s) from this provider's storage.

        Args:
            uri_template: The template URI pattern.
            version: If None, removes ALL versions. If specified, removes only that version.

        Raises:
            KeyError: If no matching template is found.
        """
        if version is None:
            # Remove all versions
            keys_to_remove = [
                k
                for k, c in self._components.items()
                if isinstance(c, ResourceTemplate) and c.uri_template == uri_template
            ]
            if not keys_to_remove:
                raise KeyError(f"Template {uri_template!r} not found")
            for key in keys_to_remove:
                self._remove_component(key)
        else:
            # Remove specific version
            key = f"{ResourceTemplate.make_key(uri_template)}@{version}"
            if key not in self._components:
                raise KeyError(
                    f"Template {uri_template!r} version {version!r} not found"
                )
            self._remove_component(key)

    def add_prompt(self, prompt: Prompt | Callable[..., Any]) -> Prompt:
        """Add a prompt to this provider's storage.

        Accepts either a Prompt object or a decorated function with __fastmcp__ metadata.
        """
        if isinstance(prompt, Prompt):
            self._add_component(prompt)
            return prompt

        # Handle decorated function with metadata
        from fastmcp.decorators import get_fastmcp_meta
        from fastmcp.prompts.function_prompt import PromptMeta

        meta = get_fastmcp_meta(prompt)
        if meta is not None and isinstance(meta, PromptMeta):
            resolved_task = meta.task if meta.task is not None else False
            enabled = meta.enabled
            prompt_obj = Prompt.from_function(
                prompt,
                name=meta.name,
                version=meta.version,
                title=meta.title,
                description=meta.description,
                icons=meta.icons,
                tags=meta.tags,
                meta=meta.meta,
                task=resolved_task,
                auth=meta.auth,
            )
        else:
            raise TypeError(
                f"Expected Prompt or @prompt-decorated function, got {type(prompt).__name__}. "
                "Use @prompt decorator or pass a Prompt instance."
            )

        self._add_component(prompt_obj)
        if not enabled:
            self.disable(keys={prompt_obj.key})
        return prompt_obj

    def remove_prompt(self, name: str, version: str | None = None) -> None:
        """Remove prompt(s) from this provider's storage.

        Args:
            name: The prompt name.
            version: If None, removes ALL versions. If specified, removes only that version.

        Raises:
            KeyError: If no matching prompt is found.
        """
        if version is None:
            # Remove all versions
            keys_to_remove = [
                k
                for k, c in self._components.items()
                if isinstance(c, Prompt) and c.name == name
            ]
            if not keys_to_remove:
                raise KeyError(f"Prompt {name!r} not found")
            for key in keys_to_remove:
                self._remove_component(key)
        else:
            # Remove specific version
            key = f"{Prompt.make_key(name)}@{version}"
            if key not in self._components:
                raise KeyError(f"Prompt {name!r} version {version!r} not found")
            self._remove_component(key)

    # =========================================================================
    # Provider interface implementation
    # =========================================================================

    async def _list_tools(self) -> Sequence[Tool]:
        """Return all tools."""
        return [v for v in self._components.values() if isinstance(v, Tool)]

    async def _get_tool(
        self, name: str, version: VersionSpec | None = None
    ) -> Tool | None:
        """Get a tool by name.

        Args:
            name: The tool name.
            version: Optional version filter. If None, returns highest version.
        """
        matching = [
            v
            for v in self._components.values()
            if isinstance(v, Tool) and v.name == name
        ]
        if version:
            matching = [t for t in matching if version.matches(t.version)]
        if not matching:
            return None
        return max(matching, key=version_sort_key)  # type: ignore[type-var]

    async def _list_resources(self) -> Sequence[Resource]:
        """Return all resources."""
        return [v for v in self._components.values() if isinstance(v, Resource)]

    async def _get_resource(
        self, uri: str, version: VersionSpec | None = None
    ) -> Resource | None:
        """Get a resource by URI.

        Args:
            uri: The resource URI.
            version: Optional version filter. If None, returns highest version.
        """
        matching = [
            v
            for v in self._components.values()
            if isinstance(v, Resource) and str(v.uri) == uri
        ]
        if version:
            matching = [r for r in matching if version.matches(r.version)]
        if not matching:
            return None
        return max(matching, key=version_sort_key)  # type: ignore[type-var]

    async def _list_resource_templates(self) -> Sequence[ResourceTemplate]:
        """Return all resource templates."""
        return [v for v in self._components.values() if isinstance(v, ResourceTemplate)]

    async def _get_resource_template(
        self, uri: str, version: VersionSpec | None = None
    ) -> ResourceTemplate | None:
        """Get a resource template that matches the given URI.

        Args:
            uri: The URI to match against templates.
            version: Optional version filter. If None, returns highest version.
        """
        # Find all templates that match the URI
        matching = [
            component
            for component in self._components.values()
            if isinstance(component, ResourceTemplate)
            and component.matches(uri) is not None
        ]
        if version:
            matching = [t for t in matching if version.matches(t.version)]
        if not matching:
            return None
        return max(matching, key=version_sort_key)  # type: ignore[type-var]

    async def _list_prompts(self) -> Sequence[Prompt]:
        """Return all prompts."""
        return [v for v in self._components.values() if isinstance(v, Prompt)]

    async def _get_prompt(
        self, name: str, version: VersionSpec | None = None
    ) -> Prompt | None:
        """Get a prompt by name.

        Args:
            name: The prompt name.
            version: Optional version filter. If None, returns highest version.
        """
        matching = [
            v
            for v in self._components.values()
            if isinstance(v, Prompt) and v.name == name
        ]
        if version:
            matching = [p for p in matching if version.matches(p.version)]
        if not matching:
            return None
        return max(matching, key=version_sort_key)  # type: ignore[type-var]

    # =========================================================================
    # Task registration
    # =========================================================================

    async def get_tasks(self) -> Sequence[FastMCPComponent]:
        """Return components eligible for background task execution.

        Returns components that have task_config.mode != 'forbidden'.
        This includes both FunctionTool/Resource/Prompt instances created via
        decorators and custom Tool/Resource/Prompt subclasses.
        """
        return [c for c in self._components.values() if c.task_config.supports_tasks()]

    # Decorator methods - implementations in decorators/ subpackage
    # Imported here to avoid circular imports and keep type checker happy
    def tool(self, *args: Any, **kwargs: Any) -> Any:
        """Tool decorator - see decorators/tool.py for implementation."""
        from fastmcp.server.providers.local_provider.decorators.tool import tool

        return tool(self, *args, **kwargs)

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        """Resource decorator - see decorators/resource.py for implementation."""
        from fastmcp.server.providers.local_provider.decorators.resource import resource

        return resource(self, *args, **kwargs)

    def prompt(self, *args: Any, **kwargs: Any) -> Any:
        """Prompt decorator - see decorators/prompt.py for implementation."""
        from fastmcp.server.providers.local_provider.decorators.prompt import prompt

        return prompt(self, *args, **kwargs)
