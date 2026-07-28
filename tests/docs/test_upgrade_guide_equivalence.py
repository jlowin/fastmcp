"""Prove the SDK v2 upgrade guides produce an equivalent server.

`test_upgrade_guide_examples.py` proves every example runs. That is necessary
but not sufficient: a migration guide is only correct if the "after" code
exposes the same MCP surface as the "before" code it replaces. A guide whose
halves both run but disagree on a tool's schema teaches a silent regression.

So for each MCP SDK v2 guide, the complete before-and-after server pair is
lifted out of the page, both halves are built, and their advertised tools,
resources, templates, and prompts are compared. The SDK v1 guides are not
covered here — v1 is not installable alongside v4, so their "before" code
cannot be built to compare against.

Run:
    uv run pytest tests/docs/test_upgrade_guide_equivalence.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pytest_examples.find_examples import _extract_code_chunks

from fastmcp import Client, FastMCP

UPGRADE_DIR = Path("docs/getting-started/upgrading")


def _block_containing(page: str, needle: str) -> dict[str, Any]:
    """Execute the one code block on `page` that contains `needle`."""
    path = UPGRADE_DIR / page
    matches = [
        ex
        for ex in _extract_code_chunks(path, path.read_text("utf-8"), uuid4())
        if needle in ex.source
    ]
    assert len(matches) == 1, (
        f"expected exactly one block in {page} containing {needle!r}, "
        f"found {len(matches)}"
    )
    namespace: dict[str, Any] = {"__name__": "fastmcp_docs_example"}
    exec(compile(matches[0].source, str(path), "exec"), namespace)
    return namespace


def _normalize(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Compare schemas by structure, ignoring generated titles.

    FastMCP derives a schema from the function signature and names it after the
    function; a hand-written schema has no title at all. That difference is
    cosmetic — the properties and required list are the contract.
    """
    if not schema:
        return {}
    properties = {
        name: {k: v for k, v in prop.items() if k != "title"}
        for name, prop in schema.get("properties", {}).items()
    }
    return {"properties": properties, "required": sorted(schema.get("required", []))}


async def _fastmcp_surface(mcp: FastMCP) -> dict[str, Any]:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
    return {
        "tools": {t.name: _normalize(t.input_schema) for t in tools},
        "resources": {str(r.uri) for r in resources},
        "templates": {t.uri_template for t in templates},
        "prompts": {p.name: sorted(a.name for a in p.arguments or []) for p in prompts},
    }


class TestMCPServerGuide:
    """docs/.../from-mcp-sdk-v2.mdx — the high-level MCPServer migration."""

    @pytest.fixture(scope="class")
    def pair(self) -> tuple[Any, FastMCP]:
        before = _block_containing("from-mcp-sdk-v2.mdx", 'MCPServer("demo")')
        after = _block_containing("from-mcp-sdk-v2.mdx", 'FastMCP("demo")')
        return before["server"], after["mcp"]

    async def test_same_surface(self, pair):
        server, mcp = pair

        before = {
            "tools": {
                t.name: _normalize(t.input_schema) for t in await server.list_tools()
            },
            "resources": {str(r.uri) for r in await server.list_resources()},
            "templates": {
                t.uri_template for t in await server.list_resource_templates()
            },
            "prompts": {
                p.name: sorted(a.name for a in p.arguments or [])
                for p in await server.list_prompts()
            },
        }

        assert before == await _fastmcp_surface(mcp)

    async def test_migrated_tools_still_work(self, pair):
        _, mcp = pair
        async with Client(mcp) as client:
            greeting = await client.call_tool("greet", {"name": "World"})
            processed = await client.call_tool("process", {"items": ["a", "b"]})

        assert greeting.data == "Hello, World!"
        assert processed.data == "Processed 2 items"


class TestLowLevelGuide:
    """docs/.../from-low-level-sdk-v2.mdx — the low-level Server migration."""

    @pytest.fixture(scope="class")
    def pair(self) -> tuple[dict[str, Any], FastMCP]:
        before = _block_containing("from-low-level-sdk-v2.mdx", '    "demo",')
        after = _block_containing("from-low-level-sdk-v2.mdx", 'FastMCP("demo")')
        return before, after["mcp"]

    async def test_same_surface(self, pair):
        handlers, mcp = pair

        tools = await handlers["list_tools"](None, None)
        resources = await handlers["list_resources"](None, None)
        prompts = await handlers["list_prompts"](None, None)
        before = {
            "tools": {t.name: _normalize(t.input_schema) for t in tools.tools},
            "resources": {str(r.uri) for r in resources.resources},
            "templates": set(),
            "prompts": {
                p.name: sorted(a.name for a in p.arguments or [])
                for p in prompts.prompts
            },
        }

        assert before == await _fastmcp_surface(mcp)

    async def test_handlers_and_tools_agree(self, pair):
        """The rewritten tool returns what the hand-written handler returned."""
        handlers, mcp = pair
        params = type(
            "Params", (), {"name": "greet", "arguments": {"name": "World"}}
        )()

        handler_result = await handlers["call_tool"](None, params)
        async with Client(mcp) as client:
            tool_result = await client.call_tool("greet", {"name": "World"})

        assert handler_result.content[0].text == "Hello, World!"
        assert tool_result.data == "Hello, World!"
