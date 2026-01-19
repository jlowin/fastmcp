"""Example: Skills Provider Server

This example shows how to expose a directory of skills as MCP resources.
Skills can be discovered, browsed, and downloaded by any MCP client.

Run this server:
    uv run python examples/skills/server.py

Then use the client example to interact with it:
    uv run python examples/skills/client.py
"""

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider

# Create server
mcp = FastMCP("Skills Server")

# Point at our sample skills directory
# Use SkillsDirectoryProvider to scan for all skills in the directory
skills_dir = Path(__file__).parent / "sample_skills"
mcp.add_provider(SkillsDirectoryProvider(root=skills_dir, reload=True))

if __name__ == "__main__":
    # Run the server (stdio transport by default)
    mcp.run()
