"""UI manager for FastMCP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.server import FastMCP
    from fastmcp.ui.openai import OpenAIUIManager


class UIManager:
    """Manager for UI-related components and integrations."""

    def __init__(self, fastmcp: FastMCP[Any]) -> None:
        self._fastmcp = fastmcp
        self._openai: OpenAIUIManager | None = None

    @property
    def openai(self) -> OpenAIUIManager:
        """Access OpenAI-specific UI components."""
        if self._openai is None:
            from fastmcp.ui.openai import OpenAIUIManager

            self._openai = OpenAIUIManager(self._fastmcp)
        return self._openai
