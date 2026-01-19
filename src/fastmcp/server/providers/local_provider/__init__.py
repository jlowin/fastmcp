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

from fastmcp.server.providers.local_provider.local_provider import (
    DuplicateBehavior,
    LocalProvider,
)

__all__ = ["DuplicateBehavior", "LocalProvider"]
