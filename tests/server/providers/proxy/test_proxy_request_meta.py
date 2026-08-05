"""Request `_meta` ownership at the proxy's backend connection boundary.

Protocol version, client identity, and client capabilities describe one
negotiated MCP connection. The proxy must never copy them from its frontend
connection onto its backend connection: a modern backend session stamps its
own values, and a handshake-era backend must not receive them at all.
Progress, tracing, task, and application metadata pass through untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mcp_types
import pytest
from mcp.client.extension import ClientExtension
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from fastmcp import Client, Context, FastMCP
from fastmcp.server.providers.proxy import FastMCPProxy, ProxyClient

FRONT_EXTENSION_ID = "example.com/frontend"
FRONT_INFO = mcp_types.Implementation(name="frontend-client", version="1.0")
BACKEND_INFO = mcp_types.Implementation(name="proxy-backend", version="1.0")
RESERVED_META_KEYS = {
    mcp_types.PROTOCOL_VERSION_META_KEY,
    mcp_types.CLIENT_INFO_META_KEY,
    mcp_types.CLIENT_CAPABILITIES_META_KEY,
}


@dataclass
class _RecordedRequest:
    protocol_version: str
    meta: dict[str, Any]


class _FrontendExtension(ClientExtension):
    identifier = FRONT_EXTENSION_ID

    def settings(self) -> dict[str, Any]:
        return {"frontend": True}


def _recording_backend(seen: dict[str, _RecordedRequest]) -> FastMCP:
    backend = FastMCP("metadata-backend")

    @backend.tool
    def inspect_tool(ctx: Context) -> str:
        request_context = ctx.request_context
        assert request_context is not None
        seen["tool"] = _RecordedRequest(
            protocol_version=request_context.protocol_version,
            meta=dict(request_context.meta or {}),
        )
        return "ok"

    return backend


def _proxy(backend: FastMCP, *, backend_mode: str) -> FastMCPProxy:
    return FastMCPProxy(
        client_factory=lambda: ProxyClient(
            backend,
            mode=backend_mode,
            client_info=BACKEND_INFO,
        )
    )


def _assert_backend_connection_meta(record: _RecordedRequest, modern: bool) -> None:
    """The backend request carries the backend connection's own envelope.

    On a handshake-era backend the reserved keys are absent. On a modern
    backend they hold the backend session's negotiated version and the proxy
    client's identity and capabilities — never the frontend client's.
    """
    meta = record.meta
    if not modern:
        assert RESERVED_META_KEYS.isdisjoint(meta)
        return

    assert meta[mcp_types.PROTOCOL_VERSION_META_KEY] == record.protocol_version
    assert meta[mcp_types.CLIENT_INFO_META_KEY] == BACKEND_INFO.model_dump(
        by_alias=True, mode="json", exclude_none=True
    )
    capabilities = meta[mcp_types.CLIENT_CAPABILITIES_META_KEY]
    assert FRONT_EXTENSION_ID not in capabilities.get("extensions", {})


@pytest.mark.parametrize(
    ("front_mode", "backend_mode", "backend_is_modern"),
    [
        ("auto", "auto", True),
        ("auto", "legacy", False),
        ("legacy", "auto", True),
        ("legacy", "legacy", False),
    ],
)
async def test_forwarded_tool_meta_stays_hop_safe(
    front_mode: str,
    backend_mode: str,
    backend_is_modern: bool,
):
    seen: dict[str, _RecordedRequest] = {}
    proxy = _proxy(_recording_backend(seen), backend_mode=backend_mode)

    async with Client(
        proxy,
        mode=front_mode,
        client_info=FRONT_INFO,
        extensions=[_FrontendExtension()],
    ) as client:
        await client.call_tool(
            "inspect_tool",
            meta={
                "progressToken": "front-progress",
                "example.com/vendor": {"request": "kept"},
            },
        )

    record = seen["tool"]
    assert (record.protocol_version in MODERN_PROTOCOL_VERSIONS) is backend_is_modern
    assert isinstance(record.meta["progressToken"], str | int)
    assert record.meta["example.com/vendor"] == {"request": "kept"}
    _assert_backend_connection_meta(record, backend_is_modern)
