"""Resolve local dependency metadata for a deployment source bundle."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from packaging.requirements import InvalidRequirement, Requirement

from fastmcp.cli.deploy.source_archive import SourceInvalidError
from fastmcp.utilities.mcp_server_config import MCPServerConfig

GENERATED_REQUIREMENTS_PATH = ".fastmcp-deploy-requirements.txt"


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
        candidate.relative_to(source_root)
    except ValueError as exc:
        raise SourceInvalidError(f"{label} leaves the source root: {value}") from exc
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceInvalidError(f"{label} does not exist: {value}") from exc
    try:
        resolved.relative_to(source_root)
    except ValueError as exc:
        raise SourceInvalidError(f"{label} leaves the source root: {value}") from exc
    if file and not candidate.is_file():
        raise SourceInvalidError(f"{label} is not a file: {value}")
    if directory and not candidate.is_dir():
        raise SourceInvalidError(f"{label} is not a directory: {value}")
    return candidate


def _resolve_dependencies(
    config: MCPServerConfig,
    source_root: Path,
    source_path: Path,
    dependency_base: Path,
) -> tuple[str | None, str | None, tuple[Path, ...]]:
    environment = config.environment
    requirements = (
        _resolve_path(
            source_root,
            _path_from_base(dependency_base, environment.requirements),
            label="Requirements file",
            file=True,
        )
        if environment.requirements is not None
        else None
    )
    project = (
        _resolve_path(
            source_root,
            _path_from_base(dependency_base, environment.project),
            label="Environment project",
            directory=True,
        )
        if environment.project is not None
        else None
    )
    project_file = (
        _resolve_path(
            source_root,
            project / "pyproject.toml",
            label="Environment project pyproject.toml",
            file=True,
        )
        if project is not None
        else None
    )
    editable = tuple(
        _resolve_path(
            source_root,
            _path_from_base(dependency_base, path),
            label="Editable dependency",
            directory=True,
        )
        for path in (environment.editable or [])
    )
    dependencies = sorted(set(environment.dependencies or []))

    if dependencies or editable or (requirements is not None and project is not None):
        lines: list[str] = []
        required: list[Path] = []
        if requirements is not None:
            lines.append(f"-r {_requirements_path(source_root, requirements)}")
            required.append(requirements)
        if project is not None and project_file is not None:
            lines.append(f"-e {_editable_path(source_root, project)}")
            required.extend((project, project_file))
        for path in sorted(
            editable, key=lambda item: _relative_path(source_root, item)
        ):
            lines.append(f"-e {_editable_path(source_root, path)}")
            required.append(path)
        for dependency in dependencies:
            rendered_dependency, local_path = _resolve_inline_dependency(
                source_root,
                dependency_base,
                dependency,
            )
            if local_path is not None:
                required.append(local_path)
            lines.append(rendered_dependency)
        return (
            GENERATED_REQUIREMENTS_PATH,
            "\n".join(lines) + "\n",
            tuple(required),
        )

    if requirements is not None:
        return _relative_path(source_root, requirements), None, (requirements,)
    if project_file is not None and project is not None:
        return _relative_path(source_root, project_file), None, (project, project_file)
    return _detect_dependency(source_root, source_path.parent)


def _path_from_base(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _detect_dependency(
    source_root: Path,
    start: Path,
) -> tuple[str | None, None, tuple[Path, ...]]:
    current = start
    while True:
        requirements = current / "requirements.txt"
        if requirements.is_file():
            return _relative_path(source_root, requirements), None, (requirements,)

        pyproject = current / "pyproject.toml"
        uv_lock = current / "uv.lock"
        if uv_lock.is_file() and pyproject.is_file():
            return (
                _relative_path(source_root, uv_lock),
                None,
                (uv_lock, pyproject),
            )
        if pyproject.is_file():
            return _relative_path(source_root, pyproject), None, (pyproject,)
        if current == source_root:
            return None, None, ()
        current = current.parent


def _resolve_inline_dependency(
    source_root: Path,
    dependency_base: Path,
    dependency: str,
) -> tuple[str, Path | None]:
    try:
        requirement = Requirement(dependency)
    except InvalidRequirement as exc:
        raise SourceInvalidError(
            f"The dependency is not a valid PEP 508 requirement: {dependency}"
        ) from exc
    if requirement.url is None:
        return dependency, None

    local_path = _resolve_local_url(source_root, dependency_base, requirement.url)
    if local_path is None:
        return dependency, None
    rendered = dependency.replace(
        requirement.url,
        _archive_local_url(source_root, local_path, requirement.url),
        1,
    )
    return rendered, local_path


def _resolve_local_url(
    source_root: Path,
    dependency_base: Path,
    reference: str,
) -> Path | None:
    parsed = urlsplit(reference)
    if parsed.scheme.endswith("+file"):
        raise SourceInvalidError("Local VCS requirement paths are not supported")
    if parsed.scheme != "file":
        return None
    if parsed.netloc not in {"", "localhost"}:
        raise SourceInvalidError("Remote file requirement paths are not supported")

    reference_path = unquote(parsed.path)
    if "$" in reference_path:
        raise SourceInvalidError("Dynamic local requirement paths are not supported")
    path = Path(reference_path).expanduser()
    if path.is_absolute():
        raise SourceInvalidError("Absolute local requirement paths are not supported")
    return _resolve_path(
        source_root,
        dependency_base / path,
        label="Local requirement path",
    )


def _requirements_path(source_root: Path, path: Path) -> str:
    relative = _relative_path(source_root, path)
    if any(character in relative for character in {'"', "'", "\\", "#", "\r", "\n"}):
        raise SourceInvalidError(
            "The requirements file path contains unsupported characters"
        )
    return (
        f'"{relative}"'
        if any(character.isspace() for character in relative)
        else relative
    )


def _editable_path(source_root: Path, path: Path) -> str:
    return f"file:{quote(_relative_path(source_root, path), safe='/')}"


def _archive_local_url(source_root: Path, path: Path, original_url: str) -> str:
    parsed = urlsplit(original_url)
    url = _editable_path(source_root, path)
    if parsed.query:
        url += f"?{parsed.query}"
    if parsed.fragment:
        url += f"#{parsed.fragment}"
    return url


def _relative_path(source_root: Path, path: Path) -> str:
    return path.relative_to(source_root).as_posix() or "."
