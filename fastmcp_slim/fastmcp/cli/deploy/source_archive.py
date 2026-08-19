"""Collect local source files and write deterministic deployment archives."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import stat
import tarfile
from pathlib import Path

import pathspec

MAX_SOURCE_UPLOAD_BYTES = 250 * 1024 * 1024
MAX_SOURCE_EXTRACTED_BYTES = 1024 * 1024 * 1024
MAX_SOURCE_ARCHIVE_MEMBERS = 25_000

_HARD_EXCLUDED_DIRECTORY_NAMES = {
    ".aws",
    ".azure",
    ".bzr",
    ".direnv",
    ".fastmcp",
    ".git",
    ".hg",
    ".kube",
    ".ssh",
    ".svn",
    "CVS",
}
_HARD_EXCLUDED_FILE_NAMES = {
    ".envrc",
    ".gitmodules",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "pip.conf",
    "pip.ini",
}
_VIRTUAL_ENVIRONMENT_NAMES = {".venv", "env", "venv", "virtualenv"}
_DEFAULT_IGNORE_SPEC = pathspec.GitIgnoreSpec.from_lines(
    (
        ".cache/",
        ".coverage",
        ".coverage.*",
        ".gitignore",
        ".hypothesis/",
        ".idea/",
        ".ipynb_checkpoints/",
        ".mypy_cache/",
        ".next/",
        ".nox/",
        ".now/",
        ".pnp*",
        ".pytest_cache/",
        ".pyre/",
        ".pytype/",
        ".ruff_cache/",
        ".tox/",
        ".vercel/",
        ".vscode/",
        ".yarn/cache/",
        "*.egg-info/",
        "*.pyc",
        "*.pyo",
        "*.swp",
        "*.swo",
        "*~",
        ".DS_Store",
        "Thumbs.db",
        "__pycache__/",
        "build/",
        "dist/",
        "htmlcov/",
        "node_modules/",
        "npm-debug.log*",
        "yarn-debug.log*",
        "yarn-error.log*",
    )
)


class SourceInvalidError(ValueError):
    """The local deployment source is invalid or unsafe."""


class ArchiveTooLargeError(ValueError):
    """The compressed source archive exceeds Horizon's upload limit."""


class _BoundedWriter:
    def __init__(self, file: io.BufferedWriter, limit: int) -> None:
        self._file = file
        self._limit = limit

    def write(self, data: bytes) -> int:
        if self._file.tell() + len(data) > self._limit:
            raise ArchiveTooLargeError(
                "The compressed source archive exceeds the 250 MB Horizon limit"
            )
        return self._file.write(data)

    def flush(self) -> None:
        self._file.flush()

    def tell(self) -> int:
        return self._file.tell()


def _collect_entries(
    source_root: Path,
    *,
    required_paths: tuple[Path, ...],
    excluded_paths: tuple[Path, ...],
) -> list[tuple[str, Path | bytes]]:
    required = _expand_required_paths(source_root, required_paths)
    excluded = {path.absolute() for path in excluded_paths}
    entries: dict[str, Path] = {}
    rules_by_directory: dict[
        Path,
        tuple[tuple[Path, pathspec.GitIgnoreSpec], ...],
    ] = {
        source_root: (
            (source_root, _DEFAULT_IGNORE_SPEC),
            *_parent_gitignore_rules(source_root),
        )
    }

    def walk_error(error: OSError) -> None:
        raise SourceInvalidError(
            f"The source directory could not be read: {error.filename or source_root}"
        ) from error

    for current_root, directory_names, file_names in os.walk(
        source_root,
        topdown=True,
        onerror=walk_error,
        followlinks=False,
    ):
        current = Path(current_root)
        rules = rules_by_directory[current]
        local_rules = _read_gitignore(source_root, current)
        if local_rules is not None:
            rules = (*rules, (current, local_rules))

        traversable: list[str] = []
        for name in sorted(directory_names):
            path = current / name
            relative = path.relative_to(source_root)
            excluded_reason = _exclusion_reason(path, relative, rules, directory=True)
            if excluded_reason is not None:
                if _contains_required(path, required):
                    raise SourceInvalidError(
                        f"Required source directory is {excluded_reason}: {relative}"
                    )
                continue
            if path.is_symlink():
                _validate_symlink(source_root, path)
                entries[relative.as_posix()] = path
            else:
                entries[relative.as_posix()] = path
                traversable.append(name)
                rules_by_directory[path] = rules
        directory_names[:] = traversable

        for name in sorted(file_names):
            path = current / name
            if path.absolute() in excluded:
                continue
            relative = path.relative_to(source_root)
            excluded_reason = _exclusion_reason(path, relative, rules)
            if excluded_reason is not None:
                if path.absolute() in required:
                    raise SourceInvalidError(
                        f"Required source file is {excluded_reason}: {relative}"
                    )
                continue
            if path.is_symlink():
                _validate_symlink(source_root, path)
            elif not stat.S_ISREG(path.stat().st_mode):
                if path.absolute() in required:
                    raise SourceInvalidError(
                        f"Required source path is not a regular file: {relative}"
                    )
                continue
            entries[relative.as_posix()] = path

    for relative, path in entries.items():
        if not path.is_symlink():
            continue
        target = _validate_symlink(source_root, path)
        if target == source_root:
            continue
        target_relative = target.relative_to(source_root).as_posix()
        if target_relative not in entries:
            raise SourceInvalidError(
                f"Symbolic link target is not archived: {relative}"
            )

    for path in required:
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(source_root).as_posix()
        resolved_relative = (
            path.resolve(strict=True).relative_to(source_root).as_posix()
        )
        if relative not in entries and resolved_relative not in entries:
            raise SourceInvalidError(f"Required source path is missing: {relative}")

    return list(entries.items())


def _expand_required_paths(
    source_root: Path,
    required_paths: tuple[Path, ...],
) -> set[Path]:
    pending = [path.absolute() for path in required_paths]
    required: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in required:
            continue
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise SourceInvalidError(
                f"Required source path leaves the source root: {path}"
            ) from exc
        required.add(path)
        resolved = _validate_symlink(source_root, path)
        if resolved != path:
            pending.append(resolved)
    return required


def _exclusion_reason(
    path: Path,
    relative: Path,
    rules: tuple[tuple[Path, pathspec.GitIgnoreSpec], ...],
    *,
    directory: bool = False,
) -> str | None:
    if _is_hard_exclusion(relative) or _is_virtual_environment(path, relative):
        return "excluded from deployment"
    if _is_ignored(path, rules, directory=directory):
        return "ignored"
    return None


def _is_virtual_environment(path: Path, relative: Path) -> bool:
    return relative.name in _VIRTUAL_ENVIRONMENT_NAMES and (
        (path / "pyvenv.cfg").is_file() or (path / "conda-meta").is_dir()
    )


def _is_hard_exclusion(relative: Path) -> bool:
    if any(part in _HARD_EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
        return True
    name = relative.name
    return (
        name in _HARD_EXCLUDED_FILE_NAMES
        or name == "fastmcp.json"
        or name.endswith(".fastmcp.json")
        or name.startswith(".env")
    )


def _contains_required(directory: Path, required_paths: set[Path]) -> bool:
    return any(
        path == directory or path.is_relative_to(directory) for path in required_paths
    )


def _parent_gitignore_rules(
    source_root: Path,
) -> tuple[tuple[Path, pathspec.GitIgnoreSpec], ...]:
    if os.path.lexists(source_root / ".git"):
        return ()
    git_root = next(
        (parent for parent in source_root.parents if os.path.lexists(parent / ".git")),
        None,
    )
    if git_root is None:
        return ()

    directories: list[Path] = []
    current = source_root.parent
    while True:
        directories.append(current)
        if current == git_root:
            break
        current = current.parent

    rules: list[tuple[Path, pathspec.GitIgnoreSpec]] = []
    for directory in reversed(directories):
        spec = _read_gitignore(git_root, directory)
        if spec is not None:
            rules.append((directory, spec))
    return tuple(rules)


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


def _is_ignored(
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


def _write_archive(
    entries: list[tuple[str, Path | bytes]],
    raw_file: io.BufferedWriter,
    source_root: Path,
) -> None:
    _validate_archive_limits(entries)
    with (
        gzip.GzipFile(
            filename="",
            fileobj=_BoundedWriter(raw_file, MAX_SOURCE_UPLOAD_BYTES),
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


def _validate_archive_limits(entries: list[tuple[str, Path | bytes]]) -> None:
    if len(entries) > MAX_SOURCE_ARCHIVE_MEMBERS:
        raise ArchiveTooLargeError(
            "The source archive exceeds the 25,000 member Horizon limit"
        )

    extracted_bytes = 0
    for _, entry_source in entries:
        if isinstance(entry_source, bytes):
            extracted_bytes += len(entry_source)
        elif not entry_source.is_symlink() and not entry_source.is_dir():
            extracted_bytes += entry_source.stat().st_size
        if extracted_bytes > MAX_SOURCE_EXTRACTED_BYTES:
            raise ArchiveTooLargeError(
                "The source archive exceeds the 1 GB extracted Horizon limit"
            )


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

    if entry_source.is_dir():
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
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
