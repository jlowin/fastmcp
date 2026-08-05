from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mcp_types
import pytest
from mcp.client.extension import ClientExtension
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from fastmcp import Client, Context, FastMCP
from fastmcp.client.request_meta import prepare_request_meta
from fastmcp.server import create_proxy
from fastmcp.server.providers.proxy import (
    FastMCPProxy,
    ProxyClient,
    ProxyProtocolPolicy,
    _create_client_factory,
)

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

    def record(operation: str, ctx: Context) -> None:
        request_context = ctx.request_context
        assert request_context is not None
        seen[operation] = _RecordedRequest(
            protocol_version=request_context.protocol_version,
            meta=dict(request_context.meta or {}),
        )

    @backend.tool
    def inspect_tool(ctx: Context) -> str:
        record("tool", ctx)
        return "ok"

    @backend.resource("data://metadata")
    def inspect_resource(ctx: Context) -> str:
        record("resource", ctx)
        return "ok"

    @backend.prompt
    def inspect_prompt(ctx: Context) -> str:
        record("prompt", ctx)
        return "ok"

    return backend


def _proxy(
    backend: FastMCP,
    *,
    backend_mode: str,
    protocol_policy: ProxyProtocolPolicy,
) -> FastMCPProxy:
    return FastMCPProxy(
        client_factory=lambda: ProxyClient(
            backend,
            mode=backend_mode,
            client_info=BACKEND_INFO,
        ),
        protocol_policy=protocol_policy,
    )


def _assert_backend_connection_meta(record: _RecordedRequest, modern: bool) -> None:
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
async def test_independent_policy_keeps_backend_negotiation_independent(
    front_mode: str,
    backend_mode: str,
    backend_is_modern: bool,
):
    seen: dict[str, _RecordedRequest] = {}
    proxy = _proxy(
        _recording_backend(seen),
        backend_mode=backend_mode,
        protocol_policy="independent",
    )

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


@pytest.mark.parametrize(
    ("front_mode", "backend_mode", "backend_is_modern"),
    [
        ("auto", "legacy", True),
        ("legacy", "auto", False),
    ],
)
async def test_mirror_policy_constrains_backend_to_frontend_era(
    front_mode: str,
    backend_mode: str,
    backend_is_modern: bool,
):
    seen: dict[str, _RecordedRequest] = {}
    proxy = _proxy(
        _recording_backend(seen),
        backend_mode=backend_mode,
        protocol_policy="mirror",
    )

    async with Client(proxy, mode=front_mode) as client:
        await client.call_tool("inspect_tool")

    record = seen["tool"]
    assert (record.protocol_version in MODERN_PROTOCOL_VERSIONS) is backend_is_modern
    _assert_backend_connection_meta(record, backend_is_modern)


@pytest.mark.parametrize("operation", ["resource", "prompt"])
async def test_non_tool_requests_forward_hop_safe_metadata(operation: str):
    seen: dict[str, _RecordedRequest] = {}
    proxy = _proxy(
        _recording_backend(seen),
        backend_mode="auto",
        protocol_policy="independent",
    )
    meta = {"example.com/vendor": {"operation": operation}}

    async with Client(proxy, mode="legacy", client_info=FRONT_INFO) as client:
        if operation == "resource":
            await client.read_resource("data://metadata", meta=meta)
        else:
            await client.get_prompt("inspect_prompt", meta=meta)

    record = seen[operation]
    assert record.meta["example.com/vendor"] == {"operation": operation}
    _assert_backend_connection_meta(record, modern=True)


def test_outbound_translation_preserves_hop_safe_metadata():
    meta = prepare_request_meta(
        {
            "progressToken": "front-progress",
            "example.com/vendor": {"request": "kept"},
            mcp_types.PROTOCOL_VERSION_META_KEY: "frontend-version",
            mcp_types.CLIENT_INFO_META_KEY: {"name": "frontend"},
            mcp_types.CLIENT_CAPABILITIES_META_KEY: {"frontend": True},
        }
    )

    assert meta is not None
    assert meta["progressToken"] == "front-progress"
    assert meta["example.com/vendor"] == {"request": "kept"}
    assert RESERVED_META_KEYS.isdisjoint(meta)


def test_client_factory_does_not_require_frontend_request_context():
    factory = _create_client_factory(FastMCP("backend"))

    client = factory()

    assert isinstance(client, Client)
    assert client.mode == "legacy"


def test_create_proxy_exposes_compatibility_policy_defaults():
    backend = FastMCP("backend")

    assert create_proxy(backend).protocol_policy == "mirror"
    assert create_proxy(backend, mode="auto").protocol_policy == "independent"
    assert create_proxy(Client(backend)).protocol_policy == "independent"
