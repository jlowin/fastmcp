from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

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


async def test_absolute_server_uses_nearest_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    write_server(project / "src" / "server.py")
    (project / "pyproject.toml").write_text("[project]\nname = 'test'\nversion = '0'\n")
    (tmp_path / "unrelated-secret.txt").write_text("secret")
    monkeypatch.chdir(tmp_path)

    bundle = await create_source_bundle(
        str(project / "src" / "server.py"),
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "src/server.py"
    assert "pyproject.toml" in archive_names(bundle.archive_path)
    assert "unrelated-secret.txt" not in archive_names(bundle.archive_path)


async def test_source_root_inherits_parent_gitignore_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    service = repository / "service"
    write_server(service / "server.py")
    (service / "requirements.txt").write_text("fastmcp>=4\n")
    (service / "private.pem").write_text("secret")
    (repository / ".git").mkdir()
    (repository / ".gitignore").write_text("*.pem\n")
    monkeypatch.chdir(repository)

    bundle = await create_source_bundle(
        "service/server.py",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "server.py"
    assert "private.pem" not in archive_names(bundle.archive_path)


async def test_source_root_inherits_repository_exclude(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    service = repository / "service"
    write_server(service / "server.py")
    (service / "requirements.txt").write_text("fastmcp>=4\n")
    (service / "private.txt").write_text("secret")
    (repository / ".git" / "info").mkdir(parents=True)
    (repository / ".git" / "info" / "exclude").write_text("service/private.txt\n")
    monkeypatch.chdir(repository)

    bundle = await create_source_bundle(
        "service/server.py",
        tmp_path / "source.tar.gz",
    )

    assert "private.txt" not in archive_names(bundle.archive_path)


async def test_worktree_uses_common_repository_exclude(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "worktree"
    write_server(project / "server.py")
    (project / "private.txt").write_text("secret")

    common_git = tmp_path / "repository.git"
    worktree_git = common_git / "worktrees" / "service"
    worktree_git.mkdir(parents=True)
    (worktree_git / "commondir").write_text("../..\n")
    (common_git / "info").mkdir()
    (common_git / "info" / "exclude").write_text("private.txt\n")
    (project / ".git").write_text(f"gitdir: {worktree_git}\n")
    monkeypatch.chdir(project)

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    assert "private.txt" not in archive_names(bundle.archive_path)


async def test_nested_repository_does_not_inherit_parent_gitignore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer = tmp_path / "outer"
    project = outer / "project"
    write_server(project / "server.py")
    (project / "private.pem").write_text("project data")
    (outer / ".git").mkdir()
    (outer / ".gitignore").write_text("*.pem\n")
    (project / ".git").mkdir()
    monkeypatch.chdir(project)

    bundle = await create_source_bundle(
        "server.py",
        tmp_path / "source.tar.gz",
    )

    assert "private.pem" in archive_names(bundle.archive_path)


async def test_absolute_server_without_project_marker_uses_server_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_directory = tmp_path / "standalone"
    write_server(source_directory / "server.py")
    (tmp_path / "unrelated-secret.txt").write_text("secret")
    monkeypatch.chdir(tmp_path)

    bundle = await create_source_bundle(
        str(source_directory / "server.py"),
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "server.py"
    assert archive_names(bundle.archive_path) == {"server.py"}


async def test_explicit_object_input_uses_selected_entrypoint(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py", name="application")

    bundle = await create_source_bundle(
        "server.py:application",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "server.py:application"


@pytest.mark.parametrize(
    ("file_name", "server_spec", "error"),
    [
        ("server.py", "server.py:not-valid", "Python identifier"),
        ("server file.py", "server file.py", "Horizon-compatible path"),
        ("server.txt", "server.txt", "Horizon-compatible path"),
    ],
)
async def test_invalid_entrypoint_is_rejected(
    project: Path,
    tmp_path: Path,
    file_name: str,
    server_spec: str,
    error: str,
) -> None:
    write_server(project / file_name)

    with pytest.raises(SourceInvalidError, match=error):
        await create_source_bundle(server_spec, tmp_path / "source.tar.gz")


async def test_missing_input_discovers_fastmcp_config(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "fastmcp.json").write_text(json.dumps({"source": {"path": "server.py"}}))

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert bundle.entrypoint == "server.py"
    assert "fastmcp.json" not in archive_names(bundle.archive_path)


@pytest.mark.parametrize("external_kind", ["source", "dependency"])
async def test_external_paths_are_rejected(
    project: Path,
    tmp_path: Path,
    external_kind: str,
) -> None:
    outside_server = tmp_path / "outside.py"
    write_server(outside_server)
    outside_requirements = tmp_path / "requirements.txt"
    outside_requirements.write_text("fastmcp>=4\n")

    if external_kind == "source":
        config = {"source": {"path": "../outside.py"}}
    else:
        write_server(project / "server.py")
        config = {
            "source": {"path": "server.py"},
            "environment": {"requirements": "../requirements.txt"},
        }
    (project / "fastmcp.json").write_text(json.dumps(config))
    server_spec = None

    with pytest.raises(SourceInvalidError, match="leaves the source root"):
        await create_source_bundle(server_spec, tmp_path / "source.tar.gz")
