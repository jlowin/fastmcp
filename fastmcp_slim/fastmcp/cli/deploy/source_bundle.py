"""Resolve and archive local source for a Horizon deployment."""

from __future__ import annotations

import json
import os
import tarfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from fastmcp.cli.deploy.source_archive import (
    ArchiveTooLargeError,
    SourceInvalidError,
    _collect_entries,
    _is_ignored,
    _parent_gitignore_rules,
    _read_gitignore,
    _sha256,
    _write_archive,
)
from fastmcp.cli.deploy.source_dependencies import (
    GENERATED_REQUIREMENTS_PATH,
    _relative_path,
    _resolve_dependencies,
    _resolve_path,
)
from fastmcp.utilities.mcp_server_config import MCPServerConfig
from fastmcp.utilities.mcp_server_config.v1.sources.filesystem import FileSystemSource

_PROJECT_ROOT_MARKERS = ("fastmcp.json", "pyproject.toml", "requirements.txt", ".git")


@dataclass(frozen=True)
class SourceBundle:
    """Metadata for a completed deployment source archive."""

    archive_path: Path
    size_bytes: int
    checksum_sha256: str
    entrypoint: str
    dependency_path: str | None


async def create_source_bundle(
    server_spec: str | None,
    archive_path: Path,
) -> SourceBundle:
    """Resolve a FastMCP server input and create its deployment archive."""
    config, source_root, config_path = _load_config(server_spec)
    resolved_archive_path = _resolve_archive_path(source_root, archive_path)
    source_base = (
        _resolve_path(
            source_root,
            config.deployment.cwd,
            label="Deployment working directory",
            directory=True,
        )
        if config_path is not None and config.deployment.cwd is not None
        else source_root
    )
    configured_source_path = Path(config.source.path).expanduser()
    source_path = _resolve_path(
        source_root,
        configured_source_path
        if configured_source_path.is_absolute()
        else source_base / configured_source_path,
        label="Server source",
        file=True,
    )
    if config.source.entrypoint and ":" in config.source.entrypoint:
        raise SourceInvalidError(
            "Deployment entrypoints must use one object from the server source file"
        )

    resolved_source = config.source.model_copy(update={"path": str(source_path)})
    try:
        object_name = resolved_source.resolve_entrypoint()
    except ValueError as exc:
        raise SourceInvalidError(str(exc)) from exc
    entrypoint = f"{_relative_path(source_root, source_path)}:{object_name}"

    dependency_path, generated_requirements, required_paths = _resolve_dependencies(
        config,
        source_root,
        source_path,
        source_base,
    )
    required_paths = (source_path, *required_paths)
    archive_created = False

    try:
        entries = _collect_entries(
            source_root,
            required_paths=required_paths,
            excluded_paths=(config_path,) if config_path is not None else (),
        )
        if generated_requirements is not None:
            generated_path = source_root / GENERATED_REQUIREMENTS_PATH
            if os.path.lexists(generated_path):
                raise SourceInvalidError(
                    f"The generated dependency path is reserved: {GENERATED_REQUIREMENTS_PATH}"
                )
            generated_rules = _parent_gitignore_rules(source_root)
            root_ignore = _read_gitignore(source_root, source_root)
            if root_ignore is not None:
                generated_rules = (*generated_rules, (source_root, root_ignore))
            if _is_ignored(generated_path, generated_rules):
                raise SourceInvalidError(
                    f"The generated dependency path is ignored: {GENERATED_REQUIREMENTS_PATH}"
                )
            entries.append(
                (GENERATED_REQUIREMENTS_PATH, generated_requirements.encode())
            )
        entries.sort(key=lambda entry: entry[0])

        resolved_archive_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw_file = resolved_archive_path.open("xb")
        except FileExistsError as exc:
            raise SourceInvalidError("The source archive path already exists") from exc
        archive_created = True
        with raw_file:
            _write_archive(entries, raw_file, source_root)
        size_bytes = resolved_archive_path.stat().st_size
        checksum = _sha256(resolved_archive_path)
    except (ArchiveTooLargeError, SourceInvalidError):
        if archive_created:
            resolved_archive_path.unlink(missing_ok=True)
        raise
    except (OSError, tarfile.TarError) as exc:
        if archive_created:
            resolved_archive_path.unlink(missing_ok=True)
        raise SourceInvalidError(
            f"The source archive could not be created: {exc}"
        ) from exc

    return SourceBundle(
        archive_path=resolved_archive_path,
        size_bytes=size_bytes,
        checksum_sha256=checksum,
        entrypoint=entrypoint,
        dependency_path=dependency_path,
    )


def _load_config(
    server_spec: str | None,
) -> tuple[MCPServerConfig, Path, Path | None]:
    if server_spec is None:
        config_path = MCPServerConfig.find_config()
        if config_path is None:
            raise SourceInvalidError(
                "Provide a server input or add fastmcp.json to the current directory"
            )
        return _load_config_file(config_path)

    if server_spec.endswith(".json"):
        return _load_config_file(Path(server_spec))

    source = FileSystemSource(path=server_spec)
    absolute_source_path = Path(os.path.abspath(Path(source.path).expanduser()))
    source_root = _find_explicit_source_root(absolute_source_path)
    if not absolute_source_path.is_relative_to(source_root):
        absolute_source_path = absolute_source_path.resolve(strict=False)
    source = source.model_copy(update={"path": str(absolute_source_path)})
    return MCPServerConfig(source=source), source_root, None


def _find_explicit_source_root(source_path: Path) -> Path:
    source_directory = source_path.parent
    if project_root := _find_project_root(source_directory):
        return project_root

    resolved_directory = source_path.resolve(strict=False).parent
    return _find_project_root(resolved_directory) or resolved_directory


def _find_project_root(start: Path) -> Path | None:
    filesystem_root = Path(start.anchor)
    home_directory = Path.home().resolve()
    for directory in (start, *start.parents):
        if directory != start and directory in {filesystem_root, home_directory}:
            break
        if any(os.path.lexists(directory / marker) for marker in _PROJECT_ROOT_MARKERS):
            return directory.resolve()
    return None


def _load_config_file(config_path: Path) -> tuple[MCPServerConfig, Path, Path]:
    try:
        resolved_path = config_path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceInvalidError(
            f"The FastMCP configuration does not exist: {config_path}"
        ) from exc
    if not resolved_path.is_file():
        raise SourceInvalidError(
            f"The FastMCP configuration is not a file: {config_path}"
        )
    try:
        config = MCPServerConfig.from_file(resolved_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise SourceInvalidError(
            f"The FastMCP configuration is invalid: {config_path}"
        ) from exc
    return config, resolved_path.parent, resolved_path


def _resolve_archive_path(source_root: Path, archive_path: Path) -> Path:
    requested = Path(archive_path).expanduser()
    if os.path.lexists(requested):
        raise SourceInvalidError("The source archive path already exists")
    try:
        resolved = requested.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise SourceInvalidError(
            "The source archive path could not be resolved"
        ) from exc
    try:
        resolved.relative_to(source_root)
    except ValueError:
        return resolved
    raise SourceInvalidError("The source archive must be outside the source root")
