"""Resolve local dependency inputs for a deployment source bundle."""

from __future__ import annotations

import os
import shlex
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
        "-i",
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
    for prefix in ("-e", "-f", "-i"):
        if option.startswith(prefix) and len(option) > len(prefix):
            if len(tokens) != 1:
                raise ValueError(f"{prefix} needs one value")
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
