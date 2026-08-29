from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from fastmcp import FastMCP
from fastmcp.server.mixins.transport import (
    _format_host_for_url,
    _resolve_allowed_hosts_for_run,
)


@pytest.mark.parametrize(
    "host, expected",
    [
        ("127.0.0.1", "127.0.0.1"),
        ("localhost", "localhost"),
        ("0.0.0.0", "0.0.0.0"),
        ("::1", "[::1]"),
        ("::", "[::]"),
        ("fe80::1", "[fe80::1]"),
        ("[::1]", "[::1]"),
    ],
)
def test_format_host_for_url(host: str, expected: str):
    """IPv6 hosts are bracketed for use in a URL; everything else is unchanged."""
    assert _format_host_for_url(host) == expected


def test_resolve_allowed_hosts_for_run_merges_configured_hosts_with_loopback_host():
    assert _resolve_allowed_hosts_for_run(
        host="127.0.0.1",
        host_origin_protection="auto",
        allowed_hosts=None,
        configured_allowed_hosts=["mcp.example.com"],
    ) == ["mcp.example.com", "127.0.0.1"]


def test_resolve_allowed_hosts_for_run_preserves_configured_hosts_when_disabled():
    assert _resolve_allowed_hosts_for_run(
        host="127.0.0.1",
        host_origin_protection=False,
        allowed_hosts=None,
        configured_allowed_hosts=["mcp.example.com"],
    ) == ["mcp.example.com"]


def test_resolve_allowed_hosts_for_run_preserves_explicit_hosts():
    assert _resolve_allowed_hosts_for_run(
        host="127.0.0.1",
        host_origin_protection="auto",
        allowed_hosts=["mcp.example.com"],
        configured_allowed_hosts=["settings.example.com"],
    ) == ["mcp.example.com"]


async def test_run_http_owns_lifespan_when_asgi_lifespan_is_disabled(
    unused_tcp_port: int,
) -> None:
    """The runner's lifecycle owner is independent of Uvicorn's ASGI mode.

    ``run_http_async`` predates the app-level lifecycle owners and remains the
    outer owner that keeps setup process-scoped for every HTTP transport. This
    guards the ownership contract retained by PR #4446.
    """
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        events.append("startup")
        try:
            yield {}
        finally:
            events.append("shutdown")

    server = FastMCP("outer-lifespan-owner", lifespan=lifespan)
    await server.run_http_async(
        transport="sse",
        host="127.0.0.1",
        port=unused_tcp_port,
        show_banner=False,
        uvicorn_config={
            "lifespan": "off",
            "limit_max_requests": 0,
            "log_level": "error",
        },
    )

    assert events == ["startup", "shutdown"]
