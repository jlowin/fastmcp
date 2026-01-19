"""Example: Downloading skills from an MCP server.

This example shows how to use the skills client utilities to discover
and download skills from any MCP server that exposes them via SkillsProvider.

Run the skills server first:
    uv run python examples/skills/server.py

Then run this script:
    uv run python examples/skills/download_skills.py
"""

import asyncio
import tempfile
from pathlib import Path

from fastmcp import Client, FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider
from fastmcp.utilities.skills import (
    download_skill,
    get_skill_manifest,
    list_skills,
    sync_skills,
)


async def main():
    # For this example, we'll create an in-memory server with skills.
    # In practice, you'd connect to a remote server URL.
    skills_dir = Path(__file__).parent / "sample_skills"
    mcp = FastMCP("Skills Server")
    mcp.add_provider(SkillsDirectoryProvider(roots=skills_dir))

    async with Client(mcp) as client:
        # 1. Discover available skills
        print("=== Available Skills ===")
        skills = await list_skills(client)
        for skill in skills:
            print(f"  {skill.name}: {skill.description}")

        # 2. Inspect a skill's manifest
        print("\n=== Manifest for pdf-processing ===")
        manifest = await get_skill_manifest(client, "pdf-processing")
        for file in manifest.files:
            print(f"  {file.path} ({file.size} bytes)")

        # 3. Download a single skill
        with tempfile.TemporaryDirectory() as tmp:
            print("\n=== Downloading pdf-processing ===")
            skill_path = await download_skill(client, "pdf-processing", tmp)
            print(f"  Downloaded to: {skill_path}")
            print("  Files:")
            for f in skill_path.rglob("*"):
                if f.is_file():
                    print(f"    {f.relative_to(skill_path)}")

        # 4. Sync all skills at once
        with tempfile.TemporaryDirectory() as tmp:
            print("\n=== Syncing all skills ===")
            paths = await sync_skills(client, tmp)
            print(f"  Downloaded {len(paths)} skills:")
            for path in paths:
                print(f"    {path.name}/")


if __name__ == "__main__":
    asyncio.run(main())
