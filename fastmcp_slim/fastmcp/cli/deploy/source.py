"""Resolve local source for a Horizon deployment."""

from __future__ import annotations

import ast
import json
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from fastmcp.cli.deploy.source_paths import (
    SourceInvalidError,
    relative_path,
    require_included_path,
    resolve_path,
)
from fastmcp.utilities.mcp_server_config import MCPServerConfig
from fastmcp.utilities.mcp_server_config.v1.sources.filesystem import FileSystemSource

GENERATED_REQUIREMENTS_PATH = ".fastmcp-deploy-requirements.txt"
_COMMON_ENTRYPOINTS = ("mcp", "server", "app")


@dataclass(frozen=True)
class DeploySource:
    """A resolved local source before archive creation."""

    source_root: Path
    entrypoint: str
    dependency_path: str | None
    generated_requirements: str | None = field(default=None, repr=False)
    required_paths: tuple[Path, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class _DependencyInput:
    path: str | None
    generated_requirements: str | None
    required_paths: tuple[Path, ...]


class _ModuleBindingVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name.partition(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name != "*":
                self.names.add(alias.asname or alias.name)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        pass

    def visit_SetComp(self, node: ast.SetComp) -> None:
        pass

    def visit_DictComp(self, node: ast.DictComp) -> None:
        pass

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


async def resolve_deploy_source(server_spec: str | None) -> DeploySource:
    """Resolve a FastMCP server input without applying runtime settings."""
    config, source_root = _load_config(server_spec)
    source_path = resolve_path(
        source_root,
        config.source.path,
        label="Server source",
        file=True,
    )
    require_included_path(source_root, source_path, label="Server source")

    if config.source.entrypoint and ":" in config.source.entrypoint:
        raise SourceInvalidError(
            "Deployment entrypoints must use a file and one object name"
        )

    object_name = _resolve_entrypoint(source_path, config.source.entrypoint)
    relative_source = source_path.relative_to(source_root).as_posix()
    dependency = _resolve_dependencies(config, source_root, source_path)
    return DeploySource(
        source_root=source_root,
        entrypoint=f"{relative_source}:{object_name}",
        dependency_path=dependency.path,
        generated_requirements=dependency.generated_requirements,
        required_paths=(source_path, *dependency.required_paths),
    )


def _resolve_entrypoint(source_path: Path, explicit_entrypoint: str | None) -> str:
    if explicit_entrypoint:
        return explicit_entrypoint

    try:
        with tokenize.open(source_path) as source_file:
            source_text = source_file.read()
        module = ast.parse(source_text, filename=str(source_path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise SourceInvalidError(
            f"The server source could not be parsed: {exc}"
        ) from exc

    bindings = _ModuleBindingVisitor()
    bindings.visit(module)
    for name in _COMMON_ENTRYPOINTS:
        if name in bindings.names:
            return name
    raise SourceInvalidError(
        "No server object named mcp, server, or app was found; provide an entrypoint"
    )


def _load_config(server_spec: str | None) -> tuple[MCPServerConfig, Path]:
    if server_spec is None:
        config_path = MCPServerConfig.find_config()
        if config_path is None:
            raise SourceInvalidError(
                "Provide a server input or add fastmcp.json to the current directory"
            )
        return _read_config(config_path), config_path.parent.resolve()

    if server_spec.endswith(".json"):
        config_path = Path(server_spec).expanduser().absolute()
        return _read_config(config_path), config_path.parent.resolve()

    return (
        MCPServerConfig(source=FileSystemSource(path=server_spec)),
        Path.cwd().resolve(),
    )


def _read_config(config_path: Path) -> MCPServerConfig:
    try:
        return MCPServerConfig.from_file(config_path)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as exc:
        raise SourceInvalidError(
            f"The FastMCP configuration is invalid: {config_path}"
        ) from exc


def _resolve_dependencies(
    config: MCPServerConfig,
    source_root: Path,
    source_path: Path,
) -> _DependencyInput:
    environment = config.environment
    requirements = (
        resolve_path(
            source_root,
            environment.requirements,
            label="Requirements file",
            file=True,
        )
        if environment.requirements is not None
        else None
    )
    project = (
        resolve_path(
            source_root,
            environment.project,
            label="Environment project",
            directory=True,
        )
        if environment.project is not None
        else None
    )
    editable = tuple(
        resolve_path(
            source_root,
            path,
            label="Editable dependency",
            directory=True,
        )
        for path in (environment.editable or [])
    )

    for label, path in (
        ("Requirements file", requirements),
        ("Environment project", project),
        *(("Editable dependency", path) for path in editable),
    ):
        if path is not None:
            require_included_path(source_root, path, label=label)

    dependencies = sorted(set(environment.dependencies or []))
    needs_generated = bool(
        dependencies or editable or (project is not None and requirements is not None)
    )
    if needs_generated:
        lines: list[str] = []
        required_paths: list[Path] = []
        if requirements is not None:
            lines.append(f"-r {relative_path(source_root, requirements)}")
            required_paths.append(requirements)
        if project is not None:
            lines.append(f"-e {relative_path(source_root, project)}")
            required_paths.append(project)
            project_config = project / "pyproject.toml"
            if project_config.is_file():
                required_paths.append(project_config)
        for path in sorted(editable, key=lambda item: relative_path(source_root, item)):
            lines.append(f"-e {relative_path(source_root, path)}")
            required_paths.append(path)
            editable_config = path / "pyproject.toml"
            if editable_config.is_file():
                required_paths.append(editable_config)
        lines.extend(dependencies)
        return _DependencyInput(
            path=GENERATED_REQUIREMENTS_PATH,
            generated_requirements="\n".join(lines) + "\n",
            required_paths=tuple(required_paths),
        )

    if requirements is not None:
        return _DependencyInput(
            path=relative_path(source_root, requirements),
            generated_requirements=None,
            required_paths=(requirements,),
        )

    if project is not None:
        dependency = _dependency_input_in(
            source_root,
            project,
            include_requirements=False,
        )
        if dependency is not None:
            return _DependencyInput(
                path=dependency.path,
                generated_requirements=None,
                required_paths=(project, *dependency.required_paths),
            )
        raise SourceInvalidError(
            "The environment project has no pyproject.toml dependency file"
        )

    return _detect_dependency_input(source_root, source_path.parent)


def _detect_dependency_input(source_root: Path, start: Path) -> _DependencyInput:
    current = start
    while True:
        dependency = _dependency_input_in(source_root, current)
        if dependency is not None:
            return dependency
        if current == source_root:
            return _DependencyInput(
                path=None,
                generated_requirements=None,
                required_paths=(),
            )
        current = current.parent


def _dependency_input_in(
    source_root: Path,
    directory: Path,
    *,
    include_requirements: bool = True,
) -> _DependencyInput | None:
    requirements = directory / "requirements.txt"
    if include_requirements and requirements.is_file():
        return _DependencyInput(
            path=relative_path(source_root, requirements),
            generated_requirements=None,
            required_paths=(requirements,),
        )

    uv_lock = directory / "uv.lock"
    pyproject = directory / "pyproject.toml"
    if uv_lock.is_file() and pyproject.is_file():
        return _DependencyInput(
            path=relative_path(source_root, uv_lock),
            generated_requirements=None,
            required_paths=(uv_lock, pyproject),
        )
    if pyproject.is_file():
        return _DependencyInput(
            path=relative_path(source_root, pyproject),
            generated_requirements=None,
            required_paths=(pyproject,),
        )
    return None
