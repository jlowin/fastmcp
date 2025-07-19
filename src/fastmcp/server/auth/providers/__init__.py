# Export all auth provider classes so that star imports (`from fastmcp.server.auth.providers import *`) work as expected and linters find the names declared in `__all__`.
from .bearer import BearerAuthProvider  # noqa: F401
from .bearer_env import EnvBearerAuthProvider  # noqa: F401
from .in_memory import InMemoryOAuthProvider  # noqa: F401
from .transparent_proxy import TransparentOAuthProxyProvider  # noqa: F401

__all__ = [
    "BearerAuthProvider",
    "EnvBearerAuthProvider",
    "InMemoryOAuthProvider",
    "TransparentOAuthProxyProvider",
]
