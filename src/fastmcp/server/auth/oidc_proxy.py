"""Backwards compatibility shim for oidc_proxy.py

The OIDCProxy class has been moved to fastmcp.server.auth.oidc_dcr_proxy.OIDCDCRProxy
for better organization. This module provides a backwards-compatible import.
"""

import warnings

import fastmcp
from fastmcp.server.auth.oidc_dcr_proxy import OIDCDCRProxy as OIDCProxy

# Re-export for backwards compatibility
__all__ = ["OIDCProxy"]

# Deprecated in 2.13
if fastmcp.settings.deprecation_warnings:
    warnings.warn(
        "The `fastmcp.server.auth.oidc_proxy` module is deprecated "
        "and will be removed in a future version. "
        "Please use `fastmcp.server.auth.oidc_dcr_proxy.OIDCDCRProxy` "
        "instead of this module's OIDCProxy.",
        DeprecationWarning,
        stacklevel=2,
    )
