"""Resolve and archive local source for a Horizon deployment."""

from __future__ import annotations

import json
import os
import shlex
import tarfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from packaging.requirements import InvalidRequirement, Requirement
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
from fastmcp.utilities.mcp_server_config import MCPServerConfig
from fastmcp.utilities.mcp_server_config.v1.sources.filesystem import FileSystemSource

GENERATED_REQUIREMENTS_PATH = ".fastmcp-deploy-requirements.txt"

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
    requirement_files = (
        _resolve_requirement_files(source_root, requirements)
        if requirements is not None
        else ()
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
            required.extend(requirement_files)
        if project is not None and project_file is not None:
            lines.append(f"-e {_editable_path(source_root, project)}")
            required.extend((project, project_file))
        for path in sorted(
            editable, key=lambda item: _relative_path(source_root, item)
        ):
            lines.append(f"-e {_editable_path(source_root, path)}")
            required.append(path)
        for dependency in dependencies:
            try:
                requirement = Requirement(dependency)
            except InvalidRequirement as exc:
                raise SourceInvalidError(
                    f"The dependency is not a valid PEP 508 requirement: {dependency}"
                ) from exc
            rendered_dependency = dependency
            if requirement.url is not None:
                local_path = _resolve_local_requirement_path(
                    source_root,
                    dependency_base / GENERATED_REQUIREMENTS_PATH,
                    requirement.url,
                )
                if local_path is not None:
                    required.append(local_path)
                    rendered_dependency = dependency.replace(
                        requirement.url,
                        _archive_local_url(
                            source_root,
                            local_path,
                            requirement.url,
                        ),
                        1,
                    )
            lines.append(rendered_dependency)
        return (
            GENERATED_REQUIREMENTS_PATH,
            "\n".join(lines) + "\n",
            tuple(required),
        )

    if requirements is not None:
        return _relative_path(source_root, requirements), None, requirement_files
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
            return (
                _relative_path(source_root, requirements),
                None,
                _resolve_requirement_files(source_root, requirements),
            )
        pyproject = current / "pyproject.toml"
        if pyproject.is_file():
            return _relative_path(source_root, pyproject), None, (pyproject,)
        if current == source_root:
            return None, None, ()
        current = current.parent


def _resolve_requirement_files(
    source_root: Path,
    requirements: Path,
) -> tuple[Path, ...]:
    required: dict[Path, None] = {}
    visiting: set[Path] = set()
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        absolute_path = path.absolute()
        required[absolute_path] = None
        resolved_path = path.resolve(strict=True)
        if resolved_path in visiting:
            relative = path.relative_to(source_root)
            raise SourceInvalidError(
                f"Requirements files contain an include cycle: {relative}"
            )
        if resolved_path in visited:
            return

        visiting.add(resolved_path)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            relative = path.relative_to(source_root)
            raise SourceInvalidError(
                f"The requirements file could not be read: {relative}"
            ) from exc

        for line_number, line in _logical_requirement_lines(content):
            try:
                requirement_line = _strip_requirement_comment(line)
                tokens = _split_requirement_tokens(requirement_line)
                reference = _requirement_reference(tokens)
                local_reference = _local_requirement_reference(
                    tokens,
                    requirement_line,
                )
            except ValueError as exc:
                relative = path.relative_to(source_root)
                raise SourceInvalidError(
                    f"Invalid requirements include at {relative}:{line_number}"
                ) from exc
            if reference is not None:
                referenced_path = _resolve_requirement_reference(
                    source_root,
                    path,
                    reference,
                )
                if referenced_path is not None:
                    visit(referenced_path)
                continue

            if local_reference is not None:
                local_path = _resolve_local_requirement_path(
                    source_root,
                    path,
                    local_reference,
                )
                if local_path is not None:
                    required[local_path.absolute()] = None

        visiting.remove(resolved_path)
        visited.add(resolved_path)

    visit(requirements)
    return tuple(required)


def _logical_requirement_lines(content: str) -> list[tuple[int, str]]:
    logical_lines: list[tuple[int, str]] = []
    continued = ""
    start_line = 1
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not continued:
            start_line = line_number
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            continued += stripped[:-1] + " "
            continue
        logical_lines.append((start_line, continued + line))
        continued = ""
    if continued:
        logical_lines.append((start_line, continued))
    return logical_lines


def _strip_requirement_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line


def _split_requirement_tokens(
    line: str,
    *,
    preserve_backslashes: bool = os.name == "nt",
) -> list[str]:
    if not preserve_backslashes:
        return shlex.split(line, comments=False, posix=True)
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""
    return list(lexer)


def _requirement_reference(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    option = tokens[0]
    if option in {"-r", "--requirement", "-c", "--constraint"}:
        if len(tokens) != 2:
            raise ValueError("A requirements include needs one path")
        return tokens[1]
    for prefix in ("--requirement=", "--constraint="):
        if option.startswith(prefix):
            if len(tokens) != 1 or not option[len(prefix) :]:
                raise ValueError("A requirements include needs one path")
            return option[len(prefix) :]
    if option.startswith(("-r", "-c")) and len(option) > 2:
        if len(tokens) != 1:
            raise ValueError("A requirements include needs one path")
        return option[2:]
    return None


def _local_requirement_reference(
    tokens: list[str],
    requirement_line: str,
) -> str | None:
    if not tokens:
        return None
    option = tokens[0]
    if option in {
        "-e",
        "--editable",
        "-f",
        "--find-links",
        "--index-url",
        "--extra-index-url",
    }:
        if len(tokens) != 2:
            raise ValueError(f"{option} needs one value")
        return tokens[1]
    for prefix in (
        "--editable=",
        "--find-links=",
        "--index-url=",
        "--extra-index-url=",
    ):
        if option.startswith(prefix):
            if len(tokens) != 1 or not option[len(prefix) :]:
                raise ValueError(f"{prefix[:-1]} needs one value")
            return option[len(prefix) :]
    if option.startswith("-"):
        return None

    try:
        requirement = Requirement(requirement_line)
    except InvalidRequirement:
        for token in tokens:
            parsed = urlsplit(token)
            has_windows_drive = len(token) > 1 and token[1] == ":"
            if parsed.scheme and not has_windows_drive:
                if parsed.scheme == "file" or parsed.scheme.endswith("+file"):
                    return token
                continue
            if token.startswith((".", "/", "~")) or any(
                separator in token for separator in ("/", "\\")
            ):
                return token
            if token.endswith((".whl", ".zip", ".tar.gz")):
                return token
        return None
    return requirement.url if requirement.url is not None else None


def _resolve_requirement_reference(
    source_root: Path,
    requirements: Path,
    reference: str,
) -> Path | None:
    referenced_path = _resolve_local_requirement_path(
        source_root,
        requirements,
        reference,
    )
    if referenced_path is None:
        return None
    if not referenced_path.is_file():
        raise SourceInvalidError(
            f"Referenced requirements file is not a file: {reference}"
        )
    return referenced_path


def _resolve_local_requirement_path(
    source_root: Path,
    requirements: Path,
    reference: str,
) -> Path | None:
    has_windows_drive = len(reference) > 1 and reference[1] == ":"
    parsed = urlsplit(reference)
    if parsed.scheme and not has_windows_drive:
        if parsed.scheme.endswith("+file"):
            raise SourceInvalidError("Local VCS requirement paths are not supported")
        if parsed.scheme != "file":
            return None
        if parsed.netloc not in {"", "localhost"}:
            raise SourceInvalidError("Remote file requirement paths are not supported")
    if not has_windows_drive:
        reference = unquote(parsed.path)
    if "$" in reference:
        raise SourceInvalidError("Dynamic local requirement paths are not supported")
    reference = _strip_local_extras(reference)

    referenced_path = Path(reference).expanduser()
    if referenced_path.is_absolute():
        raise SourceInvalidError("Absolute local requirement paths are not supported")
    referenced_path = requirements.parent / referenced_path
    return _resolve_path(
        source_root,
        referenced_path,
        label="Local requirement path",
    )


def _strip_local_extras(reference: str) -> str:
    path, separator, extras = reference.rpartition("[")
    if (
        separator
        and extras.endswith("]")
        and extras != "]"
        and all(
            character.isalnum() or character in "-_. ," for character in extras[:-1]
        )
    ):
        return path
    return reference


def _requirements_path(source_root: Path, path: Path) -> str:
    relative = _relative_path(source_root, path)
    if any(character in relative for character in {'"', "#", "\r", "\n"}):
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
