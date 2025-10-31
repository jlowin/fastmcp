"""Dependency injection exports for FastMCP.

This module re-exports dependency injection symbols from Docket and FastMCP
to provide a clean, centralized import location for all dependency-related
functionality.
"""

from docket import Depends

from fastmcp.server.dependencies import CurrentContext, CurrentDocket, CurrentWorker

__all__ = ["CurrentContext", "CurrentDocket", "CurrentWorker", "Depends"]
