from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from .bearer import BearerAuth as BearerAuth
    from .client_credentials import (
        ClientCredentialsOAuthProvider as ClientCredentialsOAuthProvider,
    )
    from .client_credentials import (
        PrivateKeyJWTOAuthProvider as PrivateKeyJWTOAuthProvider,
    )
    from .client_credentials import SignedJWTParameters as SignedJWTParameters
    from .client_credentials import (
        static_assertion_provider as static_assertion_provider,
    )
    from .oauth import OAuth as OAuth

__all__ = [
    "BearerAuth",
    "ClientCredentialsOAuthProvider",
    "OAuth",
    "PrivateKeyJWTOAuthProvider",
    "SignedJWTParameters",
    "static_assertion_provider",
]

_LAZY_IMPORTS = {
    "BearerAuth": (".bearer", "BearerAuth"),
    "ClientCredentialsOAuthProvider": (
        ".client_credentials",
        "ClientCredentialsOAuthProvider",
    ),
    "OAuth": (".oauth", "OAuth"),
    "PrivateKeyJWTOAuthProvider": (
        ".client_credentials",
        "PrivateKeyJWTOAuthProvider",
    ),
    "SignedJWTParameters": (".client_credentials", "SignedJWTParameters"),
    "static_assertion_provider": (
        ".client_credentials",
        "static_assertion_provider",
    ),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
