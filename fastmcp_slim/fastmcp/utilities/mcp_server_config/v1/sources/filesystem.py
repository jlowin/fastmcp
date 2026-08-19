import ast
import importlib.util
import inspect
import sys
import tokenize
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from fastmcp.utilities.async_utils import is_coroutine_function
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.mcp_server_config.v1.sources.base import Source

logger = get_logger(__name__)

_COMMON_ENTRYPOINTS = ("mcp", "server", "app")
_SERVER_TYPE_NAMES = {"FastMCP", "MCPServer"}
_SERVER_FACTORY_NAMES = {"create_proxy"}
_SERVER_CLASSMETHOD_NAMES = {"from_fastapi", "from_openapi"}
_SERVER_MODULE_NAMES = {
    "fastmcp",
    "fastmcp.server",
    "fastmcp.server.server",
    "mcp.server",
    "mcp.server.mcpserver",
}


def _server_binding_names(module: ast.Module) -> tuple[set[str], set[str]]:
    constructor_names: set[str] = set()
    module_names: set[str] = set()
    candidates: set[str] = set()
    uncertain_names: set[str] = set()

    for statement in module.body:
        if isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                bound_name = alias.asname or alias.name
                uncertain_names.discard(bound_name)
                _discard_bound_name(
                    bound_name,
                    candidates,
                    constructor_names,
                    module_names,
                )
                if statement.module in _SERVER_MODULE_NAMES and (
                    alias.name in _SERVER_TYPE_NAMES
                    or (
                        alias.name in _SERVER_FACTORY_NAMES
                        and statement.module
                        in {"fastmcp.server", "fastmcp.server.server"}
                    )
                ):
                    constructor_names.add(bound_name)
                elif bound_name in _COMMON_ENTRYPOINTS:
                    uncertain_names.add(bound_name)
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                uncertain_names.discard(bound_name)
                _discard_bound_name(
                    bound_name,
                    candidates,
                    constructor_names,
                    module_names,
                )
                if alias.name in _SERVER_MODULE_NAMES:
                    module_names.add(bound_name)
        elif isinstance(statement, ast.Assign):
            assigned_names = {
                name for target in statement.targets for name in _target_names(target)
            }
            uncertain_names.difference_update(assigned_names)
            is_server = _is_server_value(
                statement.value,
                constructor_names,
                module_names,
            )
            _update_assigned_names(
                assigned_names,
                is_server,
                candidates,
                constructor_names,
                module_names,
            )
            if not is_server and not _is_definitely_non_server_value(
                statement.value,
                constructor_names,
                module_names,
            ):
                uncertain_names.update(assigned_names.intersection(_COMMON_ENTRYPOINTS))
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            assigned_names = _target_names(statement.target)
            uncertain_names.difference_update(assigned_names)
            is_server = _is_server_value(
                statement.value,
                constructor_names,
                module_names,
            )
            _update_assigned_names(
                assigned_names,
                is_server,
                candidates,
                constructor_names,
                module_names,
            )
            if not is_server and not _is_definitely_non_server_value(
                statement.value,
                constructor_names,
                module_names,
            ):
                uncertain_names.update(assigned_names.intersection(_COMMON_ENTRYPOINTS))
        elif isinstance(statement, ast.AugAssign):
            assigned_names = _target_names(statement.target)
            uncertain_names.difference_update(assigned_names)
            _update_assigned_names(
                assigned_names,
                False,
                candidates,
                constructor_names,
                module_names,
            )
            uncertain_names.update(assigned_names.intersection(_COMMON_ENTRYPOINTS))
        elif isinstance(
            statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ):
            uncertain_names.discard(statement.name)
            _discard_bound_name(
                statement.name,
                candidates,
                constructor_names,
                module_names,
            )
        else:
            stored_names = _stored_names(statement)
            _update_assigned_names(
                stored_names,
                False,
                candidates,
                constructor_names,
                module_names,
            )
            uncertain_names.update(stored_names.intersection(_COMMON_ENTRYPOINTS))

    return candidates, uncertain_names


def _stored_names(node: ast.AST) -> set[str]:
    names = {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store | ast.Del)
    }
    for child in ast.walk(node):
        if isinstance(child, ast.alias):
            bound_name = child.asname or child.name.split(".", 1)[0]
        elif isinstance(
            child,
            ast.FunctionDef
            | ast.AsyncFunctionDef
            | ast.ClassDef
            | ast.ExceptHandler
            | ast.MatchAs
            | ast.MatchStar,
        ):
            bound_name = child.name
        elif isinstance(child, ast.MatchMapping):
            bound_name = child.rest
        else:
            continue
        if bound_name is not None:
            names.add(bound_name)
    return names


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.List | ast.Tuple):
        return {name for element in target.elts for name in _target_names(element)}
    return set()


def _update_assigned_names(
    assigned_names: set[str],
    is_server: bool,
    candidates: set[str],
    constructor_names: set[str],
    module_names: set[str],
) -> None:
    for name in assigned_names:
        _discard_bound_name(name, candidates, constructor_names, module_names)
        if is_server and name in _COMMON_ENTRYPOINTS:
            candidates.add(name)


def _discard_bound_name(
    name: str,
    candidates: set[str],
    constructor_names: set[str],
    module_names: set[str],
) -> None:
    candidates.discard(name)
    constructor_names.discard(name)
    module_names.discard(name)


def _is_server_value(
    value: ast.expr | None,
    constructor_names: set[str],
    module_names: set[str],
) -> bool:
    if not isinstance(value, ast.Call):
        return False
    function = value.func
    if _is_server_type_reference(function, constructor_names, module_names):
        return True
    return (
        isinstance(function, ast.Attribute)
        and function.attr in _SERVER_CLASSMETHOD_NAMES
        and _is_server_type_reference(
            function.value,
            constructor_names,
            module_names,
        )
    )


def _is_definitely_non_server_value(
    value: ast.expr,
    constructor_names: set[str],
    module_names: set[str],
) -> bool:
    if isinstance(value, ast.Constant | ast.Dict | ast.List | ast.Set | ast.Tuple):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "generate_name"
        and _is_server_type_reference(
            value.func.value,
            constructor_names,
            module_names,
        )
    )


def _is_server_type_reference(
    value: ast.expr,
    constructor_names: set[str],
    module_names: set[str],
) -> bool:
    if isinstance(value, ast.Name):
        return value.id in constructor_names
    if isinstance(value, ast.Subscript):
        return _is_server_type_reference(value.value, constructor_names, module_names)
    return (
        isinstance(value, ast.Attribute)
        and value.attr in _SERVER_TYPE_NAMES
        and _root_name(value) in module_names
    )


def _root_name(value: ast.Attribute) -> str | None:
    current: ast.expr = value
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


class FileSystemSource(Source):
    """Source for local Python files."""

    type: Literal["filesystem"] = "filesystem"

    path: str = Field(description="Path to Python file containing the server")
    entrypoint: str | None = Field(
        default=None,
        description="Name of server instance or factory function (a no-arg function that returns a FastMCP server)",
    )

    @field_validator("path", mode="before")
    @classmethod
    def parse_path_with_object(cls, v: str) -> str:
        """Parse path:object syntax and extract the object name.

        This validator runs before the model is created, allowing us to
        handle the "file.py:object" syntax at the model boundary.
        """
        if isinstance(v, str) and ":" in v:
            # Check if it's a Windows path (e.g., C:\...)
            has_windows_drive = len(v) > 1 and v[1] == ":"

            # Only split if colon is not part of Windows drive
            if ":" in (v[2:] if has_windows_drive else v):
                # This path has an object specification
                # We'll handle it in __init__ by setting entrypoint
                return v
        return v

    def __init__(self, **data: Any) -> None:
        """Initialize FileSystemSource, handling path:object syntax."""
        # Check if path contains an object specification
        if "path" in data and isinstance(data["path"], str) and ":" in data["path"]:
            path_str = data["path"]
            # Check if it's a Windows path (e.g., C:\...)
            has_windows_drive = len(path_str) > 1 and path_str[1] == ":"

            # Only split if colon is not part of Windows drive
            if ":" in (path_str[2:] if has_windows_drive else path_str):
                file_str, obj = path_str.rsplit(":", 1)
                data["path"] = file_str
                # Only set entrypoint if not already provided
                if "entrypoint" not in data or data["entrypoint"] is None:
                    data["entrypoint"] = obj

        super().__init__(**data)

    async def load_server(self) -> Any:
        """Load server from filesystem."""
        file_path = Path(self.path).expanduser().resolve()
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        if not file_path.is_file():
            logger.error(f"Not a file: {file_path}")
            sys.exit(1)

        module = self._import_module(file_path)
        return await self._find_server_object(module, file_path)

    def resolve_entrypoint(self) -> str:
        """Resolve an explicit or statically verified common entrypoint."""
        if self.entrypoint:
            return self.entrypoint

        file_path = Path(self.path).expanduser().resolve()
        try:
            with tokenize.open(file_path) as source_file:
                module = ast.parse(source_file.read(), filename=str(file_path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise ValueError(f"Could not inspect server source: {file_path}") from exc

        candidates, uncertain_names = _server_binding_names(module)
        for name in _COMMON_ENTRYPOINTS:
            if name in uncertain_names:
                break
            if name in candidates:
                return name
        raise ValueError(
            "No statically verified server binding named mcp, server, or app was found; "
            "provide an explicit entrypoint"
        )

    def _import_module(self, file_path: Path) -> Any:
        """Import a Python module from a file path.

        Args:
            file_path: Path to the Python file

        Returns:
            The imported module
        """
        # Add parent directory to Python path so imports can be resolved
        file_dir = str(file_path.parent)
        if file_dir not in sys.path:
            sys.path.insert(0, file_dir)

        # Import the module
        spec = importlib.util.spec_from_file_location("server_module", file_path)
        if not spec or not spec.loader:
            logger.error("Could not load module", extra={"file": str(file_path)})
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        sys.modules["server_module"] = module  # Register in sys.modules
        spec.loader.exec_module(module)

        return module

    async def _find_server_object(self, module: Any, file_path: Path) -> Any:
        """Find the server object in the module."""
        # Avoid circular import by importing here
        from mcp.server.mcpserver import MCPServer as SDKServer

        from fastmcp.server.server import FastMCP

        # If entrypoint is specified, use it
        if self.entrypoint:
            # Handle module:object syntax (though this is legacy)
            if ":" in self.entrypoint:
                module_name, object_name = self.entrypoint.split(":", 1)
                try:
                    import importlib

                    server_module = importlib.import_module(module_name)
                    obj = getattr(server_module, object_name, None)
                except ImportError:
                    logger.error(
                        f"Could not import module '{module_name}'",
                        extra={"file": str(file_path)},
                    )
                    sys.exit(1)
            else:
                # Just object name
                obj = getattr(module, self.entrypoint, None)

            if obj is None:
                logger.error(
                    f"Server object '{self.entrypoint}' not found",
                    extra={"file": str(file_path)},
                )
                sys.exit(1)

            return await self._resolve_factory(obj, file_path, self.entrypoint)

        # No entrypoint specified, try common server names
        for name in ["mcp", "server", "app"]:
            if hasattr(module, name):
                obj = getattr(module, name)
                if isinstance(obj, FastMCP | SDKServer):
                    return await self._resolve_factory(obj, file_path, name)

        # No server found
        logger.error(
            f"No server object found in {file_path}. Please either:\n"
            "1. Use a standard variable name (mcp, server, or app)\n"
            "2. Specify the entrypoint name in fastmcp.json or use `file.py:object` syntax as your path.",
            extra={"file": str(file_path)},
        )
        sys.exit(1)

    async def _resolve_factory(self, obj: Any, file_path: Path, name: str) -> Any:
        """Resolve a server object or factory function to a server instance.

        Args:
            obj: The object that might be a server or factory function
            file_path: Path to the file for error messages
            name: Name of the object for error messages

        Returns:
            A server instance
        """
        # Avoid circular import by importing here
        from mcp.server.mcpserver import MCPServer as SDKServer

        from fastmcp.server.server import FastMCP

        # Check if it's a function or coroutine function
        if inspect.isfunction(obj) or is_coroutine_function(obj):
            logger.debug(f"Found factory function '{name}' in {file_path}")

            try:
                if is_coroutine_function(obj):
                    # Async factory function
                    server = await obj()
                else:
                    # Sync factory function
                    server = obj()

                # Validate the result is a FastMCP server
                if not isinstance(server, FastMCP | SDKServer):
                    logger.error(
                        f"Factory function '{name}' must return a FastMCP server instance, "
                        f"got {type(server).__name__}",
                        extra={"file": str(file_path)},
                    )
                    sys.exit(1)

                logger.debug(f"Factory function '{name}' created server: {server.name}")
                return server

            except Exception as e:
                logger.error(
                    f"Failed to call factory function '{name}': {e}",
                    extra={"file": str(file_path)},
                )
                sys.exit(1)

        # Not a function, return as-is (should be a server instance)
        return obj
