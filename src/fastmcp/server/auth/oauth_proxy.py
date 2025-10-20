"""Backwards compatibility shim for oauth_proxy.py

The OauthProxy class has been moved to fastmcp.server.auth.oauth_dcr_proxy.OAuthDCRProxy
for better organization. This module provides a backwards-compatible import.
"""

import warnings

import fastmcp
from fastmcp.server.auth.oauth_dcr_proxy import OAuthDCRProxy as OAuthProxy

# Re-export for backwards compatibility
__all__ = ["OAuthProxy"]

# Deprecated in 2.13
if fastmcp.settings.deprecation_warnings:
    warnings.warn(
        "The `fastmcp.server.auth.oauth_proxy` module is deprecated "
        "and will be removed in a future version. "
        "Please use `fastmcp.server.auth.oauth_dcr_proxy.OAuthDCRProxy` "
        "instead of this module's OAuthProxy.",
        DeprecationWarning,
        stacklevel=2,
    )
