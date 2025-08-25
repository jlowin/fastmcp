"""External Resources for FastMCP.

This module provides a safe, controlled, and scalable approach to exposing
external data to LLMs using MCP as a gateway protocol.

Key components:
- ExternalResource: Declares specific external resources
- ExternalResourceTemplate: Declares patterns for external resources
- ValidationMiddleware: Optional middleware to enforce access control
- register_external_resources: Helper to register multiple resources
"""

from .resources import (
    ExternalResource,
    ExternalResourceTemplate,
    register_external_resources,
)
from .validation_middleware import ValidationMiddleware

__all__ = [
    "ExternalResource",
    "ExternalResourceTemplate",
    "register_external_resources",
    "ValidationMiddleware",
]
