"""Decorator methods for LocalProvider."""

from fastmcp.server.providers.local_provider.decorators.prompt import prompt
from fastmcp.server.providers.local_provider.decorators.resource import resource
from fastmcp.server.providers.local_provider.decorators.tool import tool

__all__ = ["prompt", "resource", "tool"]
