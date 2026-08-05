"""Typed negotiation results that retain protocol extension fields."""

import mcp_types
from pydantic import ConfigDict


class _ExtensibleInitializeResult(mcp_types.InitializeResult):
    model_config = ConfigDict(extra="allow")


class _ExtensibleDiscoverResult(mcp_types.DiscoverResult):
    model_config = ConfigDict(extra="allow")
