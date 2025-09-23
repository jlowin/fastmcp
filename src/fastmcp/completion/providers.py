"""
FastMCP-specific completion providers for Prompts and Resources.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.prompts import Prompt
    from fastmcp.resources import Resource, ResourceTemplate


class CompletionProvider(ABC):
    """Base class for FastMCP completion providers."""

    @abstractmethod
    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        """
        Generate completion suggestions for the given partial input.

        Args:
            partial: The partial input string to complete
            context: MCP context with 'ref', 'argument', and 'server'

        Returns:
            List of completion suggestions (prompt/resource names)
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class PromptCompletion(CompletionProvider):
    """Completion provider that suggests available FastMCP prompts."""

    def __init__(self, filter_fn: Callable[["Prompt"], bool] | None = None):
        """
        Initialize prompt completion provider.

        Args:
            filter_fn: Optional function to filter which prompts to include
        """
        self.filter_fn = filter_fn

    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        if not context or "server" not in context:
            return []

        server: FastMCP = context["server"]
        prompts = await server._prompt_manager.list_prompts()

        # Apply filter if provided
        if self.filter_fn:
            prompts = [p for p in prompts if self.filter_fn(p)]

        # Get prompt names
        prompt_names = [p.key for p in prompts]

        # Filter by partial match
        if partial:
            prompt_names = [
                name
                for name in prompt_names
                if name.lower().startswith(partial.lower())
            ]

        return prompt_names

    def __repr__(self) -> str:
        return f"PromptCompletion(filter_fn={self.filter_fn})"


class ResourceCompletion(CompletionProvider):
    """Completion provider that suggests available FastMCP resources."""

    def __init__(self, filter_fn: Callable[["Resource"], bool] | None = None):
        """
        Initialize resource completion provider.

        Args:
            filter_fn: Optional function to filter which resources to include
        """
        self.filter_fn = filter_fn

    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        if not context or "server" not in context:
            return []

        server: FastMCP = context["server"]
        resources = await server._resource_manager.list_resources()

        # Apply filter if provided
        if self.filter_fn:
            resources = [r for r in resources if self.filter_fn(r)]

        # Get resource URIs as strings
        resource_uris = [str(r.uri) for r in resources]

        # Filter by partial match
        if partial:
            resource_uris = [
                uri for uri in resource_uris if uri.lower().startswith(partial.lower())
            ]

        return resource_uris

    def __repr__(self) -> str:
        return f"ResourceCompletion(filter_fn={self.filter_fn})"


class ResourceTemplateCompletion(CompletionProvider):
    """Completion provider that suggests available FastMCP resource templates."""

    def __init__(self, filter_fn: Callable[["ResourceTemplate"], bool] | None = None):
        """
        Initialize resource template completion provider.

        Args:
            filter_fn: Optional function to filter which templates to include
        """
        self.filter_fn = filter_fn

    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        if not context or "server" not in context:
            return []

        server: FastMCP = context["server"]
        templates = await server._resource_manager.list_resource_templates()

        # Apply filter if provided
        if self.filter_fn:
            templates = [t for t in templates if self.filter_fn(t)]

        # Get template URI templates as strings
        template_uris = [str(t.uri_template) for t in templates]

        # Filter by partial match
        if partial:
            template_uris = [
                uri for uri in template_uris if uri.lower().startswith(partial.lower())
            ]

        return template_uris

    def __repr__(self) -> str:
        return f"ResourceTemplateCompletion(filter_fn={self.filter_fn})"


class StaticCompletion(CompletionProvider):
    """Static completion provider with predefined choices (for simple cases)."""

    def __init__(self, choices: list[str]):
        """
        Initialize with a list of static choices.

        Args:
            choices: List of possible completion values
        """
        self.choices = choices

    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        if not partial:
            return self.choices
        return [c for c in self.choices if c.lower().startswith(partial.lower())]

    def __repr__(self) -> str:
        return f"StaticCompletion({self.choices!r})"
