from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

import fastmcp.cli.deploy.source_dependencies as source_dependencies_module
from fastmcp.cli.deploy.source_bundle import SourceInvalidError, create_source_bundle


def write_server(path: Path, name: str = "mcp") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from fastmcp import FastMCP\n"
        f'{name} = FastMCP("Test")\n'
        f"@{name}.tool\n"
        "def ping() -> str:\n"
        '    return "pong"\n'
    )


def archive_names(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as archive:
        return {member.name for member in archive.getmembers()}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source_root = tmp_path / "project"
    source_root.mkdir()
    monkeypatch.chdir(source_root)
    return source_root


async def test_nested_requirement_and_constraint_files_are_required(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    requirements_directory = project / "requirements"
    requirements_directory.mkdir()
    (project / "requirements.txt").write_text("--requirement requirements/base.txt\n")
    (requirements_directory / "base.txt").write_text("-c constraints.txt\nhttpx\n")
    (requirements_directory / "constraints.txt").write_text("httpx<1\n")

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    assert bundle.dependency_path == "requirements.txt"
    assert {
        "requirements.txt",
        "requirements/base.txt",
        "requirements/constraints.txt",
    } <= archive_names(bundle.archive_path)


async def test_ignored_nested_requirement_file_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text("-r requirements/base.txt\n")
    (project / "requirements").mkdir()
    (project / "requirements" / "base.txt").write_text("httpx\n")
    (project / ".gitignore").write_text("requirements/base.txt\n")

    with pytest.raises(SourceInvalidError, match="Required source file is ignored"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_requirement_include_cycle_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text("-r requirements/base.txt\n")
    (project / "requirements").mkdir()
    (project / "requirements" / "base.txt").write_text("-r ../requirements.txt\n")

    with pytest.raises(SourceInvalidError, match="include cycle"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_external_nested_requirement_file_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text("-r ../outside.txt\n")
    (tmp_path / "outside.txt").write_text("httpx\n")

    with pytest.raises(SourceInvalidError, match="leaves the source root"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


@pytest.mark.parametrize(
    "requirement",
    [
        "package @ https://example.com/${TOKEN}/package.whl",
        "-r https://example.com/${TOKEN}/requirements.txt",
    ],
)
async def test_remote_requirement_environment_variable_is_preserved(
    project: Path,
    tmp_path: Path,
    requirement: str,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text(f"{requirement}\n")

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    assert bundle.dependency_path == "requirements.txt"


async def test_local_editable_with_extras_is_required(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text("-e .[postgres]\n")

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    assert bundle.dependency_path == "requirements.txt"


def test_requirement_tokens_preserve_windows_path_separators() -> None:
    assert source_dependencies_module._split_requirement_tokens(
        r'-r "requirements\base file.txt"',
        preserve_backslashes=True,
    ) == ["-r", r"requirements\base file.txt"]


@pytest.mark.parametrize(
    "requirement",
    [
        "-e ../shared",
        "-e../shared",
        "-f../shared",
        "-i ../shared",
        "-i../shared",
        "../shared",
        "shared @ file:../shared",
        'shared @ file:../shared ; python_version < "3.12"',
        "--find-links ../shared",
        "--index-url file:../shared",
        "--extra-index-url=file:../shared",
    ],
)
async def test_external_local_requirement_path_is_rejected(
    project: Path,
    tmp_path: Path,
    requirement: str,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text(f"{requirement}\n")
    (tmp_path / "shared").mkdir()

    with pytest.raises(SourceInvalidError, match="leaves the source root"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_ignored_local_dependency_content_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    wheels = project / "wheels"
    wheels.mkdir()
    (wheels / "package.whl").write_bytes(b"wheel")
    (project / "requirements.txt").write_text("--no-index\n--find-links wheels\n")
    (project / ".gitignore").write_text("*.whl\n")

    with pytest.raises(SourceInvalidError, match="Required source file is ignored"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_hashed_external_local_requirement_path_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (tmp_path / "package.whl").write_bytes(b"wheel")
    (project / "requirements.txt").write_text(
        "package @ file:../package.whl --hash=sha256:abc\n"
    )

    with pytest.raises(SourceInvalidError, match="leaves the source root"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_bare_local_vcs_requirement_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text("git+file:../shared#egg=shared\n")

    with pytest.raises(SourceInvalidError, match="Local VCS requirement"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_absolute_local_requirement_path_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    package = project / "package"
    package.mkdir()
    (project / "requirements.txt").write_text(f"-e {package}\n")

    with pytest.raises(SourceInvalidError, match="Absolute local requirement"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")
