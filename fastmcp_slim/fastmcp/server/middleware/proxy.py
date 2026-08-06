"""Negotiation metadata forwarding for MCP proxy gateways."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import mcp_types
from mcp.shared.exceptions import MCPError
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from fastmcp.client.client import Client
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from fastmcp.server.providers.proxy import ProxyProvider

logger = get_logger(__name__)

ProxyIdentity = Literal["proxy", "upstream"]


@dataclass(frozen=True)
class _NegotiationMetadata:
    instructions: str | None
    server_info: mcp_types.Implementation | None
    meta: dict[str, Any]

    @classmethod
    def from_client(cls, client: Client) -> _NegotiationMetadata | None:
        result = client.session.initialize_result or client.session.discover_result
        if result is None:
            return None
        return cls(
            instructions=result.instructions,
            server_info=client.session.server_info,
            meta=dict(result.meta or {}),
        )


class ProxyNegotiationMetadataMiddleware(Middleware):
    """Forward optional negotiation metadata from a ``ProxyProvider`` backend.

    The frontend always owns protocol versions, capabilities, cache policy, and
    result type. Instructions and namespaced metadata are filled from the
    backend only where the frontend has no value. ``identity`` controls whether
    server identity remains the gateway's or is replaced by the backend's.
    """

    def __init__(
        self,
        provider: ProxyProvider,
        *,
        identity: ProxyIdentity = "proxy",
    ) -> None:
        if identity not in ("proxy", "upstream"):
            raise ValueError("identity must be 'proxy' or 'upstream'")
        self.client_factory = provider.client_factory
        self.identity = identity

    async def _read_upstream(
        self, context: MiddlewareContext[Any]
    ) -> _NegotiationMetadata | None:
        from fastmcp.server.providers.proxy import (
            _PROXY_TRANSPORT_ERRORS,
            _stash_proxy_request_context,
        )

        try:
            client = self.client_factory()
            if inspect.isawaitable(client):
                client = cast(Client, await client)

            if client.is_connected():
                return _NegotiationMetadata.from_client(client)

            # Metadata negotiation is independent of component operations. Use a
            # fresh session so a factory that returns one reusable disconnected
            # client is neither mutated nor made unavailable to a concurrent call.
            client = client.new()

            # A pinned modern client adopts a synthesized DiscoverResult without
            # contacting the server. Metadata reads need the real result, so probe
            # modern discovery and retain its normal legacy fallback instead.
            if client.mode in MODERN_PROTOCOL_VERSIONS:
                client.mode = "auto"

            if context.fastmcp_context is not None:
                _stash_proxy_request_context(client, context.fastmcp_context)
            async with client:
                return _NegotiationMetadata.from_client(client)
        except (MCPError, *_PROXY_TRANSPORT_ERRORS) as error:
            logger.debug("Could not read upstream negotiation metadata: %r", error)
            return None

    def _merge_meta(
        self,
        frontend_meta: dict[str, Any],
        upstream: _NegotiationMetadata,
    ) -> dict[str, Any]:
        # Identity is handled as a policy, not an ordinary `_meta` collision.
        # In particular, a modern backend's identity stamp must not leak onto a
        # legacy frontend while `identity="proxy"` keeps the canonical field.
        merged = {
            key: value
            for key, value in upstream.meta.items()
            if key != mcp_types.SERVER_INFO_META_KEY
        }
        merged.update(frontend_meta)
        if self.identity == "upstream" and upstream.server_info is not None:
            merged[mcp_types.SERVER_INFO_META_KEY] = upstream.server_info.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )
        return merged

    def _updates(
        self,
        result: mcp_types.InitializeResult | mcp_types.DiscoverResult,
        upstream: _NegotiationMetadata,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "meta": self._merge_meta(dict(result.meta or {}), upstream) or None
        }
        if result.instructions is None and upstream.instructions is not None:
            updates["instructions"] = upstream.instructions
        if (
            isinstance(result, mcp_types.InitializeResult)
            and self.identity == "upstream"
            and upstream.server_info is not None
        ):
            updates["server_info"] = upstream.server_info
        return updates

    async def on_initialize(
        self,
        context: MiddlewareContext[mcp_types.InitializeRequest],
        call_next: CallNext[
            mcp_types.InitializeRequest, mcp_types.InitializeResult | None
        ],
    ) -> mcp_types.InitializeResult | None:
        result = await call_next(context)
        if result is None:
            return None
        upstream = await self._read_upstream(context)
        if upstream is None:
            return result
        return result.model_copy(update=self._updates(result, upstream))

    async def on_discover(
        self,
        context: MiddlewareContext[mcp_types.DiscoverRequest],
        call_next: CallNext[mcp_types.DiscoverRequest, mcp_types.DiscoverResult],
    ) -> mcp_types.DiscoverResult:
        result = await call_next(context)
        upstream = await self._read_upstream(context)
        if upstream is None:
            return result
        return result.model_copy(update=self._updates(result, upstream))
