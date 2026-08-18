"""Resolve and archive local source for a Horizon deployment."""

from __future__ import annotations

import ast
import gzip
import hashlib
import io
import json
import os
import stat
import tarfile
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

import pathspec
from pydantic import ValidationError

from fastmcp.utilities.mcp_server_config import MCPServerConfig
from fastmcp.utilities.mcp_server_config.v1.sources.filesystem import FileSystemSource

MAX_SOURCE_UPLOAD_BYTES = 250 * 1024 * 1024
GENERATED_REQUIREMENTS_PATH = ".fastmcp-deploy-requirements.txt"

_EXCLUDED_DIRECTORY_NAMES = {
    ".fastmcp",
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "env",
    "venv",
    "virtualenv",
}
_EXCLUDED_FILE_NAMES = {".DS_Store"}
_EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo"}
_COMMON_ENTRYPOINTS = ("mcp", "server", "app")


class SourceInvalidError(ValueError):
    """The local deployment source is invalid or unsafe."""


class ArchiveTooLargeError(ValueError):
    """The compressed source archive exceeds Horizon's upload limit."""


class _CompressedSizeWriter:
    def __init__(self, file: io.BufferedWriter) -> None:
        self._file = file

    def write(self, data: bytes) -> int:
        if self._file.tell() + len(data) > MAX_SOURCE_UPLOAD_BYTES:
            raise ArchiveTooLargeError(
                "The compressed source archive exceeds the 250 MB Horizon limit"
            )
        return self._file.write(data)

    def flush(self) -> None:
        self._file.flush()


@dataclass(frozen=True)
class DeploySource:
    """A resolved local source before archive creation."""

    source_root: Path
    entrypoint: str
    dependency_path: str | None
    _generated_requirements: str | None = field(default=None, repr=False)
    _required_paths: tuple[Path, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class SourceBundle:
    """An immutable archive ready for source upload."""

    archive_path: Path
    size_bytes: int
    checksum_sha256: str
    entrypoint: str
    dependency_path: str | None


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
    source_path = _resolve_path(
        source_root,
        config.source.path,
        label="Server source",
        file=True,
    )
    _require_included_path(source_root, source_path, label="Server source")

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
        _generated_requirements=dependency.generated_requirements,
        _required_paths=(source_path, *dependency.required_paths),
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


def create_source_bundle(
    source: DeploySource,
    archive_path: Path,
) -> SourceBundle:
    """Create a deterministic source archive and return its upload metadata."""
    source_root = source.source_root.resolve(strict=True)
    try:
        archive_path = Path(archive_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise SourceInvalidError(
            "The source archive path could not be resolved"
        ) from exc
    try:
        archive_path.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise SourceInvalidError("The source archive must be outside the source root")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    entries = _archive_entries(
        source_root,
        archive_path,
        required_paths=source._required_paths,
    )
    if source._generated_requirements is not None:
        generated_path = source_root / GENERATED_REQUIREMENTS_PATH
        if os.path.lexists(generated_path):
            raise SourceInvalidError(
                f"The generated dependency path is reserved: {GENERATED_REQUIREMENTS_PATH}"
            )
        entries.append(
            (GENERATED_REQUIREMENTS_PATH, source._generated_requirements.encode())
        )
    entries.sort(key=lambda entry: entry[0])

    try:
        with (
            archive_path.open("wb") as raw_file,
            gzip.GzipFile(
                filename="",
                fileobj=_CompressedSizeWriter(raw_file),
                mode="wb",
                mtime=0,
            ) as gzip_file,
            tarfile.open(
                fileobj=gzip_file,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive,
        ):
            for name, entry_source in entries:
                _add_archive_entry(archive, name, entry_source, source_root)
    except (ArchiveTooLargeError, SourceInvalidError):
        archive_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        archive_path.unlink(missing_ok=True)
        raise SourceInvalidError(
            f"The source archive could not be created: {exc}"
        ) from exc

    size_bytes = archive_path.stat().st_size
    return SourceBundle(
        archive_path=archive_path,
        size_bytes=size_bytes,
        checksum_sha256=_sha256(archive_path),
        entrypoint=source.entrypoint,
        dependency_path=source.dependency_path,
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
        _resolve_path(
            source_root,
            environment.requirements,
            label="Requirements file",
            file=True,
        )
        if environment.requirements is not None
        else None
    )
    project = (
        _resolve_path(
            source_root,
            environment.project,
            label="Environment project",
            directory=True,
        )
        if environment.project is not None
        else None
    )
    editable = tuple(
        _resolve_path(
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
            _require_included_path(source_root, path, label=label)

    dependencies = sorted(set(environment.dependencies or []))
    needs_generated = bool(
        dependencies or editable or (project is not None and requirements is not None)
    )
    if needs_generated:
        lines: list[str] = []
        required_paths: list[Path] = []
        if requirements is not None:
            lines.append(f"-r {_relative_path(source_root, requirements)}")
            required_paths.append(requirements)
        if project is not None:
            lines.append(f"-e {_relative_path(source_root, project)}")
            required_paths.append(project)
            project_config = project / "pyproject.toml"
            if project_config.is_file():
                required_paths.append(project_config)
        for path in sorted(
            editable, key=lambda item: _relative_path(source_root, item)
        ):
            lines.append(f"-e {_relative_path(source_root, path)}")
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
            path=_relative_path(source_root, requirements),
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
            path=_relative_path(source_root, requirements),
            generated_requirements=None,
            required_paths=(requirements,),
        )

    uv_lock = directory / "uv.lock"
    pyproject = directory / "pyproject.toml"
    if uv_lock.is_file() and pyproject.is_file():
        return _DependencyInput(
            path=_relative_path(source_root, uv_lock),
            generated_requirements=None,
            required_paths=(uv_lock, pyproject),
        )
    if pyproject.is_file():
        return _DependencyInput(
            path=_relative_path(source_root, pyproject),
            generated_requirements=None,
            required_paths=(pyproject,),
        )
    return None


def _resolve_path(
    source_root: Path,
    value: str | Path,
    *,
    label: str,
    file: bool = False,
    directory: bool = False,
) -> Path:
    requested = Path(value).expanduser()
    candidate = Path(
        os.path.abspath(
            requested if requested.is_absolute() else source_root / requested
        )
    )
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceInvalidError(f"{label} does not exist: {value}") from exc
    try:
        resolved.relative_to(source_root)
    except ValueError:
        raise SourceInvalidError(f"{label} leaves the source root: {value}") from None
    if file and not candidate.is_file():
        raise SourceInvalidError(f"{label} is not a file: {value}")
    if directory and not candidate.is_dir():
        raise SourceInvalidError(f"{label} is not a directory: {value}")
    return candidate


def _require_included_path(source_root: Path, path: Path, *, label: str) -> None:
    relative = path.relative_to(source_root)
    if _is_fixed_exclusion(relative):
        raise SourceInvalidError(f"{label} is excluded from deployment: {relative}")


def _relative_path(source_root: Path, path: Path) -> str:
    relative = path.relative_to(source_root).as_posix()
    return relative or "."


def _archive_entries(
    source_root: Path,
    archive_path: Path,
    *,
    required_paths: tuple[Path, ...],
) -> list[tuple[str, Path | bytes]]:
    required = _expand_required_paths(source_root, required_paths)
    required_directories = {path for path in required if path.is_dir()}
    entries: dict[str, Path] = {}
    rules_by_directory: dict[
        Path,
        tuple[tuple[Path, pathspec.GitIgnoreSpec], ...],
    ] = {source_root: ()}

    for current_root, directory_names, file_names in os.walk(
        source_root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_root)
        rules = rules_by_directory[current]
        local_rules = _read_gitignore(source_root, current)
        if local_rules is not None:
            rules = (*rules, (current, local_rules))

        traversable_directories: list[str] = []
        for name in sorted(directory_names):
            path = current / name
            relative = path.relative_to(source_root)
            if _is_fixed_exclusion(relative):
                continue
            if _is_gitignored(path, rules, directory=True):
                if any(
                    required.is_relative_to(path) for required in required_directories
                ):
                    raise SourceInvalidError(
                        f"Required source directory is ignored: {relative}"
                    )
                continue
            if path.is_symlink():
                _validate_symlink(source_root, path)
                entries[relative.as_posix()] = path
            else:
                traversable_directories.append(name)
                rules_by_directory[path] = rules
        directory_names[:] = traversable_directories

        for name in sorted(file_names):
            path = current / name
            if path.absolute() == archive_path:
                continue
            relative = path.relative_to(source_root)
            if _is_fixed_exclusion(relative):
                continue
            if path.absolute() not in required and _is_gitignored(path, rules):
                continue
            if path.is_symlink():
                _validate_symlink(source_root, path)
            elif not path.is_file():
                continue
            entries[relative.as_posix()] = path

    for path in required:
        relative = path.relative_to(source_root)
        if path.is_dir():
            continue
        if not path.is_file():
            raise SourceInvalidError(f"Required source file is missing: {relative}")
        entries[relative.as_posix()] = path

    return list(entries.items())


def _expand_required_paths(
    source_root: Path,
    required_paths: tuple[Path, ...],
) -> set[Path]:
    pending = list(required_paths)
    required: set[Path] = set()
    while pending:
        path = pending.pop().absolute()
        if path in required:
            continue
        _require_included_path(source_root, path, label="Required source path")
        required.add(path)
        if path.is_symlink():
            pending.append(_validate_symlink(source_root, path))
    return required


def _read_gitignore(
    source_root: Path,
    directory: Path,
) -> pathspec.GitIgnoreSpec | None:
    gitignore = directory / ".gitignore"
    if not gitignore.is_file():
        return None
    if gitignore.is_symlink():
        _validate_symlink(source_root, gitignore)
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        relative = gitignore.relative_to(source_root)
        raise SourceInvalidError(
            f"The .gitignore file could not be read: {relative}"
        ) from exc
    return pathspec.GitIgnoreSpec.from_lines(lines)


def _is_gitignored(
    path: Path,
    rules: tuple[tuple[Path, pathspec.GitIgnoreSpec], ...],
    *,
    directory: bool = False,
) -> bool:
    ignored = False
    for base, spec in rules:
        relative = path.relative_to(base).as_posix()
        result = spec.check_file(relative + "/" if directory else relative)
        if result.include is not None:
            ignored = result.include
    return ignored


def _is_fixed_exclusion(relative: Path) -> bool:
    parts = relative.parts
    if any(part in _EXCLUDED_DIRECTORY_NAMES for part in parts[:-1]):
        return True
    name = relative.name
    return (
        name in _EXCLUDED_DIRECTORY_NAMES
        or name in _EXCLUDED_FILE_NAMES
        or name == ".env"
        or name.startswith(".env.")
        or relative.suffix in _EXCLUDED_FILE_SUFFIXES
    )


def _validate_symlink(source_root: Path, path: Path) -> Path:
    try:
        target = path.resolve(strict=True)
        target.relative_to(source_root)
    except (OSError, RuntimeError, ValueError):
        relative = path.relative_to(source_root)
        raise SourceInvalidError(
            f"Symbolic link leaves the source root: {relative}"
        ) from None
    return target


def _add_archive_entry(
    archive: tarfile.TarFile,
    name: str,
    entry_source: Path | bytes,
    source_root: Path,
) -> None:
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}

    if isinstance(entry_source, bytes):
        info.mode = 0o644
        info.size = len(entry_source)
        archive.addfile(info, io.BytesIO(entry_source))
        return

    if entry_source.is_symlink():
        target = _validate_symlink(source_root, entry_source)
        info.type = tarfile.SYMTYPE
        info.mode = 0o777
        info.linkname = os.path.relpath(target, entry_source.parent).replace(
            os.sep, "/"
        )
        archive.addfile(info)
        return

    file_stat = entry_source.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise SourceInvalidError(f"Source entry is not a regular file: {name}")
    info.mode = 0o755 if file_stat.st_mode & 0o111 else 0o644
    info.size = file_stat.st_size
    with entry_source.open("rb") as source_file:
        archive.addfile(info, source_file)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archive_file:
        for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
