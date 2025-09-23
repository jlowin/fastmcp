"""
FastMCP-specific completion providers for Prompts and Resources.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any


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

class FuzzyCompletion(CompletionProvider):
    """Fuzzy matching completion provider."""

    def __init__(self, choices: list[str]):
        self.choices = choices

    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        if not partial:
            return []
        return [c for c in self.choices if partial.lower() in c.lower()]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

class DynamicCompletion(CompletionProvider):
    """Dynamic completion provider using a callable."""

    def __init__(self, completion_fn: Callable[[str], Awaitable[list[str]]]):
        self.completion_fn = completion_fn

    async def complete(
        self, partial: str, context: dict[str, Any] | None = None
    ) -> list[str]:
        return await self.completion_fn(partial)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
