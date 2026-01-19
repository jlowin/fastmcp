"""Skills providers for exposing agent skills as MCP resources.

This module provides a two-layer architecture for skill discovery:

- **SkillProvider**: Handles a single skill folder, exposing its files as resources.
- **SkillsDirectoryProvider**: Scans a directory, creates a SkillProvider per folder.
- **ClaudeSkillsProvider**: Convenience subclass for Claude Code skills.

Example:
    ```python
    from pathlib import Path
    from fastmcp import FastMCP
    from fastmcp.server.providers.skills import ClaudeSkillsProvider, SkillProvider

    mcp = FastMCP("Skills Server")

    # Load a single skill
    mcp.add_provider(SkillProvider(Path.home() / ".claude/skills/pdf-processing"))

    # Or load all skills in a directory
    mcp.add_provider(ClaudeSkillsProvider())  # Uses ~/.claude/skills/
    ```
"""

from __future__ import annotations

# Import shared utilities first
from fastmcp.server.providers.skills._common import (
    SkillFileInfo,
    SkillInfo,
    compute_file_hash,
    parse_frontmatter,
    scan_skill_files,
)

# Import providers
from fastmcp.server.providers.skills.claude_provider import ClaudeSkillsProvider
from fastmcp.server.providers.skills.directory_provider import SkillsDirectoryProvider
from fastmcp.server.providers.skills.skill_provider import (
    SkillFileResource,
    SkillFileTemplate,
    SkillProvider,
    SkillResource,
)


# Backwards compatibility alias
SkillsProvider = SkillsDirectoryProvider


__all__ = [
    "ClaudeSkillsProvider",
    "SkillFileInfo",
    "SkillFileResource",
    "SkillFileTemplate",
    "SkillInfo",
    "SkillProvider",
    "SkillResource",
    "SkillsDirectoryProvider",
    "SkillsProvider",  # Backwards compatibility alias
    "compute_file_hash",
    "parse_frontmatter",
    "scan_skill_files",
]
