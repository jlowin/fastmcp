"""Check the API claims the upgrade guides make against the real APIs.

The other two doc tests cover code blocks: one executes them, one compares the
before/after pair. Neither looks at *prose*, and prose is where a migration
guide does most of its work — mapping tables, prompt checklists, and sentences
naming an attribute to use. Those claims went wrong repeatedly and in the same
way: an API was named without anyone checking it resolved.

So this file checks the claims mechanically:

- every ``ctx.<name>`` the guides tell a reader to *use* exists on the class
  they'd be using it on, and every one they name as removed really is gone
- every ``MCPServer`` constructor parameter appears somewhere in the SDK v2
  guide, so a newly added SDK argument can't quietly go unmapped
- the ``request_context`` attributes the guides route people to are real

Run:
    uv run pytest tests/docs/test_upgrade_guide_api_claims.py -v
"""

from __future__ import annotations

import inspect
import re
import warnings
from pathlib import Path

import pytest

UPGRADE_DIR = Path("docs/getting-started/upgrading")


def _guide(name: str) -> str:
    return (UPGRADE_DIR / name).read_text("utf-8")


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from mcp.server.mcpserver import MCPServer

    from fastmcp import Context as FastMCPContext


# Context attributes the guides may mention without them existing on FastMCP's
# Context, because the guide's whole point is that they are gone or moved. Each
# is asserted to genuinely be absent, so a name that later gains an
# implementation stops being listed as missing.
DOCUMENTED_AS_ABSENT = {
    "sample",
    "sample_step",
    "list_roots",
    "mcp_server",
    "headers",
    "protocol_version",
    "client_capabilities",
    "elicit_url",
    "close_standalone_sse_stream",
    "notify_tools_changed",
    "notify_resources_changed",
    "notify_prompts_changed",
    "notify_resource_updated",
    "params",
    "meta",
}


def test_absent_context_attributes_are_really_absent():
    """Names the guides describe as gone must not exist on FastMCP's Context.

    If one of these gains an implementation, the guides are now telling people
    to work around something that works, and this test says so.
    """
    resurrected = [
        n for n in sorted(DOCUMENTED_AS_ABSENT) if hasattr(FastMCPContext, n)
    ]
    assert not resurrected, (
        f"guides describe these as absent from fastmcp.Context, but they exist: {resurrected}"
    )


@pytest.mark.parametrize(
    "guide",
    sorted(p.name for p in UPGRADE_DIR.glob("*.mdx")),
)
def test_ctx_attributes_named_in_guides_exist(guide: str):
    """Every ``ctx.<name>`` in a guide either exists or is documented as absent."""
    referenced = set(re.findall(r"`ctx\.([a-z_]+)", _guide(guide)))
    unknown = {
        name
        for name in referenced
        if not hasattr(FastMCPContext, name) and name not in DOCUMENTED_AS_ABSENT
    }
    assert not unknown, (
        f"{guide} names ctx.{{{', '.join(sorted(unknown))}}}, which do not exist on "
        f"fastmcp.Context and are not in DOCUMENTED_AS_ABSENT"
    )


def test_request_context_attributes_the_guides_route_to_exist():
    """The guides send people to ``ctx.request_context`` for several attributes.

    ``FastMCPRequestContext`` resolves its attributes dynamically, so this is
    checked against a live request rather than the class.
    """
    import asyncio

    from fastmcp import Client, FastMCP

    mcp = FastMCP("probe")

    @mcp.tool
    async def probe(ctx: FastMCPContext) -> list[str]:
        rc = ctx.request_context
        return [n for n in ("request_id", "meta", "protocol_version") if hasattr(rc, n)]

    async def run() -> list[str]:
        async with Client(mcp) as client:
            return (await client.call_tool("probe", {})).data

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        present = asyncio.run(run())

    assert set(present) == {"request_id", "meta", "protocol_version"}


def test_every_mcpserver_constructor_param_is_mapped():
    """The SDK v2 guide claims an exhaustive constructor mapping — hold it to that.

    A parameter added to ``MCPServer`` upstream should fail here rather than
    reach a reader as an unmapped keyword that raises ``TypeError`` on FastMCP.
    """
    guide = _guide("from-mcp-sdk-v2.mdx")
    params = [
        p for p in inspect.signature(MCPServer.__init__).parameters if p != "self"
    ]

    unmapped = []
    for param in params:
        # `warn_on_duplicate_resources` is covered by the table's shorthand
        # "warn_on_duplicate_tools, _resources, _prompts".
        shorthand = param.replace("warn_on_duplicate", "")
        if re.search(rf"`{re.escape(param)}[=`]", guide):
            continue
        if param.startswith("warn_on_duplicate") and re.search(
            rf"`{re.escape(shorthand)}`", guide
        ):
            continue
        unmapped.append(param)

    assert not unmapped, (
        f"MCPServer constructor parameters not mentioned in from-mcp-sdk-v2.mdx: {unmapped}"
    )
