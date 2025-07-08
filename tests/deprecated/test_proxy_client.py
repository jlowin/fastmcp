"""
Deprecation tests for FastMCPProxy client parameter.

These tests can be safely deleted when the deprecated client parameter is removed.
Deprecated in v2.10.3
"""

import warnings

import pytest

from fastmcp import Client, FastMCP

# reset deprecation warnings for this module
pytestmark = pytest.mark.filterwarnings("default::DeprecationWarning")


def test_fastmcp_proxy_client_deprecation_warning():
    """Test that FastMCPProxy with client parameter raises a deprecation warning."""
    from fastmcp.server.proxy import FastMCPProxy

    server = FastMCP("TestServer")
    client = Client(server)

    with pytest.warns(
        DeprecationWarning,
        match="Passing a Client instance to FastMCPProxy is deprecated",
    ):
        FastMCPProxy(client=client)


def test_fastmcp_proxy_client_factory_no_warning():
    """Test that FastMCPProxy with client_factory parameter does not raise a warning."""
    from fastmcp.server.proxy import FastMCPProxy

    server = FastMCP("TestServer")
    client = Client(server)

    # This should not raise a warning since we're using the new API
    with warnings.catch_warnings(record=True) as recorded_warnings:
        FastMCPProxy(client_factory=lambda: client)

        # Verify no deprecation warnings were raised
        deprecation_warnings = [
            w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0
