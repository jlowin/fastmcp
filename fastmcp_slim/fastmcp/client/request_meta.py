"""Preparation of request metadata at the outbound MCP connection boundary."""

from __future__ import annotations

from typing import Any, cast

import mcp_types

from fastmcp.telemetry import inject_trace_context

_CONNECTION_META_KEYS = frozenset(
    {
        mcp_types.PROTOCOL_VERSION_META_KEY,
        mcp_types.CLIENT_INFO_META_KEY,
        mcp_types.CLIENT_CAPABILITIES_META_KEY,
    }
)


def prepare_request_meta(
    meta: dict[str, Any] | None,
) -> mcp_types.RequestParamsMeta | None:
    """Prepare hop-safe metadata for a new outbound MCP connection.

    Protocol version, client identity, and client capabilities describe one MCP
    connection, so they cannot be copied onto another. The negotiated client
    session adds its own values on modern connections; legacy connections leave
    them absent. Progress, tracing, task, and application metadata survive.
    """
    forwarded = {
        key: value
        for key, value in (meta or {}).items()
        if key not in _CONNECTION_META_KEYS
    }
    return cast(
        "mcp_types.RequestParamsMeta | None",
        inject_trace_context(forwarded or None) or None,
    )
