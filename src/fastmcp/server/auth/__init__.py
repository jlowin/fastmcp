from .auth import (
    OAuthProvider,
    TokenVerifier,
    RemoteAuthProvider,
    AccessToken,
    AuthProvider,
)
from .providers.jwt import JWTVerifier, StaticTokenVerifier
from .oauth_dcr_proxy import OAuthDCRProxy

import warnings
import fastmcp

__all__ = [
    "AuthProvider",
    "OAuthProvider",
    "TokenVerifier",
    "JWTVerifier",
    "StaticTokenVerifier",
    "RemoteAuthProvider",
    "AccessToken",
    "OAuthDCRProxy",
]


def __getattr__(name: str):
    # Defer import because it raises a deprecation warning
    if name == "BearerAuthProvider":
        from .providers.bearer import BearerAuthProvider

        return BearerAuthProvider

    if name == "OAuthProxy":
        from .oauth_dcr_proxy import OAuthDCRProxy as OAuthProxy

        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "The `OAuthProxy` class is deprecated "
                "and has been replaced by `OAuthDCRProxy`. "
                "This import will be removed in a future version.",
                DeprecationWarning,
                stacklevel=2,
            )
        return OAuthProxy

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
