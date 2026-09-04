"""FastMCP server with optional, in-process FastAPI route integration.

Set ``MCP_FASTAPI_APP`` to an import string such as ``app.main:app`` to
expose that application's safe OpenAPI routes as MCP tools.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import pkgutil
from base64 import b64decode
from typing import Any

from fastapi import FastAPI

from fastmcp import Context, FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import Image

logger = logging.getLogger(__name__)

DEFAULT_APP_IMPORT = "app.main:app"
DEFAULT_SERVER_NAME = "Lightspeed MCP Server"
BLOCKED_PREFIXES = (
    "system",
    "service",
    "mcp_deny",
    "users",
    "user",
    "password-recovery",
    "reset-password",
    "debug",
    "admin",
    "messaging",
    "metrics",
    "private",
)
BLOCKED_PATTERNS = (
    "signup",
    "password",
    "token",
    "admin",
    "debug",
    "superuser",
    "delete",
    "reset",
    "recovery",
)
PIXEL_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


def _alternation(values: tuple[str, ...]) -> str:
    """Build a regex alternation from trusted, module-level path fragments."""
    return "|".join(values)


def safe_route_maps() -> list[RouteMap]:
    """Exclude sensitive routes without mutating the FastAPI application."""
    return [
        RouteMap(methods=["DELETE", "PUT", "PATCH"], mcp_type=MCPType.EXCLUDE),
        RouteMap(
            pattern=rf"(?i)^/(?:{_alternation(BLOCKED_PREFIXES)})(?:/|$)",
            mcp_type=MCPType.EXCLUDE,
        ),
        RouteMap(
            pattern=rf"(?i).*(?:{_alternation(BLOCKED_PATTERNS)}).*",
            mcp_type=MCPType.EXCLUDE,
        ),
    ]


def load_fastapi_app(import_string: str | None = None) -> FastAPI | None:
    """Load a FastAPI app from ``module:attribute``.

    A missing default app is allowed for standalone use. A bad app explicitly
    supplied through the argument or environment fails fast.
    """
    configured_import = import_string or os.getenv(
        "MCP_FASTAPI_APP", DEFAULT_APP_IMPORT
    )
    module_name, separator, attribute = configured_import.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("MCP_FASTAPI_APP must use the form 'module:attribute'")

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        app_was_implicit = import_string is None and "MCP_FASTAPI_APP" not in os.environ
        missing_app_module = exc.name in {module_name, module_name.split(".")[0]}
        if app_was_implicit and missing_app_module:
            logger.info(
                "No FastAPI app found at %s; using standalone mode", configured_import
            )
            return None
        raise RuntimeError(f"Could not import FastAPI module {module_name!r}") from exc

    app = getattr(module, attribute, None)
    if not isinstance(app, FastAPI):
        raise TypeError(
            f"{configured_import!r} does not resolve to a FastAPI application"
        )
    return app


def _component_package_names() -> tuple[str, ...]:
    prefix = f"{__package__}." if __package__ else ""
    return tuple(f"{prefix}{name}" for name in ("tools", "prompts", "resources"))


def register_local_components(server: FastMCP) -> list[str]:
    """Discover modules and call their ``register_*`` functions once."""
    registered: list[str] = []
    for package_name in _component_package_names():
        try:
            package = importlib.import_module(package_name)
        except ModuleNotFoundError:
            logger.debug("Component package %s is not importable", package_name)
            continue

        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            continue

        for module_info in pkgutil.walk_packages(package_paths, f"{package_name}."):
            parts = module_info.name.removeprefix(f"{package_name}.").split(".")
            if any(part.startswith("_") for part in parts):
                continue
            module = importlib.import_module(module_info.name)
            for name, candidate in inspect.getmembers(module, inspect.isfunction):
                if (
                    name.startswith("register_")
                    and candidate.__module__ == module.__name__
                ):
                    candidate(server)
                    registered.append(f"{module.__name__}.{name}")
    return registered


def add_builtin_components(server: FastMCP) -> None:
    """Register the built-in image and resource smoke-test components."""

    @server.tool
    async def add(a: int, b: int, ctx: Context | None = None) -> ToolResult:
        """Add two numbers and return a tiny image plus a structured sum."""
        result = a + b
        if ctx:
            await ctx.info(f"Addition result: {result}")
        return ToolResult(
            content=[Image(data=PIXEL_PNG, format="png").to_image_content()],
            structured_content={"sum": result},
        )

    @server.resource("config://app-version")
    async def get_app_version(ctx: Context | None = None) -> str:
        """Return the integration package version."""
        if ctx:
            await ctx.info("Returning app version v2.0.0")
        return "v2.0.0"


def build_server(
    fastapi_app: FastAPI | None = None,
    *,
    name: str = DEFAULT_SERVER_NAME,
    discover_components: bool = True,
) -> FastMCP:
    """Build a FastMCP 3 server, optionally backed by FastAPI."""
    server = (
        FastMCP.from_fastapi(
            app=fastapi_app,
            name=name,
            route_maps=safe_route_maps(),
        )
        if fastapi_app is not None
        else FastMCP(name)
    )
    if discover_components:
        registered = register_local_components(server)
        logger.info("Registered %d local component modules", len(registered))
    add_builtin_components(server)
    return server


def create_http_app(path: str = "/mcp") -> Any:
    """Return an ASGI app for Uvicorn or Gunicorn deployments."""
    return mcp.http_app(path=path)


os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("FASTMCP_TELEMETRY_ENABLED", "false")
mcp = build_server(load_fastapi_app())


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", os.getenv("PORT", "8000")))
    path = os.getenv("MCP_PATH", "/mcp")
    mcp.run(transport="http", host=host, port=port, path=path)
