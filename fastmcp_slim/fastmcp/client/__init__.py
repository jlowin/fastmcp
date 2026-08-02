from typing import TYPE_CHECKING

from fastmcp import _install_hints
from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from .auth import (
        BearerAuth as BearerAuth,
    )
    from .auth import (
        ClientCredentialsOAuthProvider as ClientCredentialsOAuthProvider,
    )
    from .auth import (
        OAuth as OAuth,
    )
    from .auth import (
        PrivateKeyJWTOAuthProvider as PrivateKeyJWTOAuthProvider,
    )
    from .client import Client as Client
    from .transports import (
        ClientTransport as ClientTransport,
    )
    from .transports import (
        FastMCPTransport as FastMCPTransport,
    )
    from .transports import (
        NodeStdioTransport as NodeStdioTransport,
    )
    from .transports import (
        NpxStdioTransport as NpxStdioTransport,
    )
    from .transports import (
        PythonStdioTransport as PythonStdioTransport,
    )
    from .transports import (
        SSETransport as SSETransport,
    )
    from .transports import (
        StdioTransport as StdioTransport,
    )
    from .transports import (
        StreamableHttpTransport as StreamableHttpTransport,
    )
    from .transports import (
        UvStdioTransport as UvStdioTransport,
    )
    from .transports import (
        UvxStdioTransport as UvxStdioTransport,
    )

__all__ = [
    "BearerAuth",
    "Client",
    "ClientCredentialsOAuthProvider",
    "ClientTransport",
    "FastMCPTransport",
    "NodeStdioTransport",
    "NpxStdioTransport",
    "OAuth",
    "PrivateKeyJWTOAuthProvider",
    "PythonStdioTransport",
    "SSETransport",
    "StdioTransport",
    "StreamableHttpTransport",
    "UvStdioTransport",
    "UvxStdioTransport",
]

_LAZY_IMPORTS = {
    "BearerAuth": (".auth", "BearerAuth"),
    "Client": (".client", "Client"),
    "ClientCredentialsOAuthProvider": (
        ".auth",
        "ClientCredentialsOAuthProvider",
    ),
    "ClientTransport": (".transports", "ClientTransport"),
    "FastMCPTransport": (".transports", "FastMCPTransport"),
    "NodeStdioTransport": (".transports", "NodeStdioTransport"),
    "NpxStdioTransport": (".transports", "NpxStdioTransport"),
    "OAuth": (".auth", "OAuth"),
    "PrivateKeyJWTOAuthProvider": (".auth", "PrivateKeyJWTOAuthProvider"),
    "PythonStdioTransport": (".transports", "PythonStdioTransport"),
    "SSETransport": (".transports", "SSETransport"),
    "StdioTransport": (".transports", "StdioTransport"),
    "StreamableHttpTransport": (".transports", "StreamableHttpTransport"),
    "UvStdioTransport": (".transports", "UvStdioTransport"),
    "UvxStdioTransport": (".transports", "UvxStdioTransport"),
}


def __getattr__(name: str) -> object:
    try:
        return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)
    except ImportError as exc:
        raise ImportError(_install_hints.CLIENT_SUPPORT) from exc


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
