"""Dependency injection exports for FastMCP.

This module re-exports dependency injection symbols from Docket and FastMCP
to provide a clean, centralized import location for all dependency-related
functionality.
"""

from docket import Depends

__all__ = ["Depends"]
