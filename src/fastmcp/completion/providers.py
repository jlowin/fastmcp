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
