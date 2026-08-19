from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

import pytest

import fastmcp.cli.deploy.source_archive as source_archive_module
import fastmcp.cli.deploy.source_bundle as source_bundle_module
from fastmcp.cli.deploy.source_bundle import (
    ArchiveTooLargeError,
    SourceInvalidError,
    create_source_bundle,
)


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


async def test_explicit_server_resolves_entrypoint_and_dependency(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "src" / "server.py")
    (project / "requirements.txt").write_text("fastmcp>=4\n")

    bundle = await create_source_bundle(
        "src/server.py",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "src/server.py:mcp"
    assert bundle.dependency_path == "requirements.txt"
    assert bundle.size_bytes == bundle.archive_path.stat().st_size
    assert len(bundle.checksum_sha256) == 64
    assert {"src/server.py", "requirements.txt"} <= archive_names(bundle.archive_path)


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

    assert bundle.entrypoint == "src/server.py:mcp"
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

    assert bundle.entrypoint == "server.py:mcp"
    assert "private.pem" not in archive_names(bundle.archive_path)


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

    assert bundle.entrypoint == "server.py:mcp"
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


async def test_explicit_config_uses_its_directory_as_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "project"
    monkeypatch.delenv("TOKEN", raising=False)
    write_server(source_root / "src" / "server.py", name="app")
    (source_root / "requirements.txt").write_text("fastmcp>=4\n")
    config_path = source_root / "deploy.json"
    config_path.write_text(
        json.dumps(
            {
                "source": {"path": "src/server.py", "entrypoint": "app"},
                "environment": {"requirements": "requirements.txt"},
                "deployment": {"env": {"TOKEN": "not-archived"}},
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    bundle = await create_source_bundle(
        "project/deploy.json",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "src/server.py:app"
    assert bundle.dependency_path == "requirements.txt"
    assert "deploy.json" not in archive_names(bundle.archive_path)
    assert "TOKEN" not in os.environ


async def test_config_source_resolves_from_deployment_working_directory(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "src" / "server.py")
    (project / "src" / "requirements.txt").write_text("fastmcp>=4\n")
    (project / "requirements.txt").write_text("wrong-package\n")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"requirements": "requirements.txt"},
                "deployment": {"cwd": "src"},
            }
        )
    )

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert bundle.entrypoint == "src/server.py:mcp"
    assert bundle.dependency_path == "src/requirements.txt"


async def test_missing_input_discovers_fastmcp_config(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "fastmcp.json").write_text(json.dumps({"source": {"path": "server.py"}}))

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert bundle.entrypoint == "server.py:mcp"
    assert "fastmcp.json" not in archive_names(bundle.archive_path)


async def test_configured_dependency_is_not_imported_locally(
    project: Path,
    tmp_path: Path,
) -> None:
    side_effect = project / "side-effect"
    (project / "server.py").write_text(
        "import deployment_only_dependency\n"
        "from pathlib import Path\n"
        "from fastmcp import FastMCP\n"
        f"Path({str(side_effect)!r}).touch()\n"
        'mcp = FastMCP("Static")\n'
    )
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"dependencies": ["deployment-only-dependency"]},
            }
        )
    )

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert bundle.entrypoint == "server.py:mcp"
    assert bundle.dependency_path == ".fastmcp-deploy-requirements.txt"
    assert not side_effect.exists()


async def test_combined_dependencies_create_generated_requirements(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements-base.txt").write_text("fastmcp>=4\n")
    package = project / "package"
    package.mkdir()
    (package / "pyproject.toml").write_text('[project]\nname = "package"\n')
    (package / "package.py").write_text("PACKAGE = True\n")
    editable = project / "shared package"
    editable.mkdir()
    (editable / "shared.py").write_text("SHARED = True\n")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {
                    "requirements": "requirements-base.txt",
                    "project": "package",
                    "editable": ["shared package"],
                    "dependencies": ["pydantic>=2", "httpx>=0.27", "httpx>=0.27"],
                },
            }
        )
    )

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    dependency_path = bundle.dependency_path
    assert dependency_path == ".fastmcp-deploy-requirements.txt"
    with tarfile.open(bundle.archive_path, "r:gz") as archive:
        generated = archive.extractfile(dependency_path)
        assert generated is not None
        assert generated.read().decode() == (
            "-r requirements-base.txt\n"
            "-e file:package\n"
            "-e file:shared%20package\n"
            "httpx>=0.27\n"
            "pydantic>=2\n"
        )
    assert {
        "package/pyproject.toml",
        "package/package.py",
        "shared package/shared.py",
    } <= archive_names(bundle.archive_path)


async def test_inline_local_dependency_is_rewritten_from_deployment_cwd(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "src" / "server.py")
    (project / "shared").mkdir()
    (project / "shared" / "pyproject.toml").write_text(
        "[project]\nname = 'shared'\nversion = '0'\n"
    )
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"dependencies": ["shared @ file:../shared"]},
                "deployment": {"cwd": "src"},
            }
        )
    )

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    dependency_path = bundle.dependency_path
    assert dependency_path is not None
    with tarfile.open(bundle.archive_path, "r:gz") as archive:
        generated = archive.extractfile(dependency_path)
        assert generated is not None
        assert generated.read().decode() == "shared @ file:shared\n"


async def test_project_dependency_uses_pyproject(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "src" / "server.py")
    (project / "pyproject.toml").write_text('[project]\nname = "project"\n')
    (project / "uv.lock").write_text("version = 1\n")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "src/server.py"},
                "environment": {"project": "."},
            }
        )
    )

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert bundle.dependency_path == "pyproject.toml"
    assert "uv.lock" in archive_names(bundle.archive_path)


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
    assert source_bundle_module._split_requirement_tokens(
        r'-r "requirements\base file.txt"',
        preserve_backslashes=True,
    ) == ["-r", r"requirements\base file.txt"]


@pytest.mark.parametrize(
    "requirement",
    [
        "-e ../shared",
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


async def test_archive_is_deterministic(project: Path, tmp_path: Path) -> None:
    write_server(project / "server.py")
    executable = project / "start.sh"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)

    first = await create_source_bundle("server.py", tmp_path / "first.tar.gz")
    second = await create_source_bundle("server.py", tmp_path / "second.tar.gz")

    assert first.checksum_sha256 == second.checksum_sha256
    assert first.archive_path.read_bytes() == second.archive_path.read_bytes()
    with tarfile.open(first.archive_path, "r:gz") as archive:
        server = archive.getmember("server.py")
        script = archive.getmember("start.sh")
        assert (server.uid, server.gid, server.uname, server.gname) == (0, 0, "", "")
        assert server.mtime == 0
        assert server.mode == 0o644
        assert script.mode == 0o755


async def test_archive_applies_secret_and_ignore_exclusions(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "keep.txt").write_text("keep")
    (project / "ignored.txt").write_text("ignored")
    (project / ".gitignore").write_text("*.txt\n")
    app = project / "app"
    app.mkdir()
    (app / ".gitignore").write_text("!keep.txt\n")
    (app / "keep.txt").write_text("keep")
    (app / "env").mkdir()
    (app / "env" / "settings.py").write_text("DEBUG = False\n")
    (project / ".env").write_text("TOKEN=secret\n")
    (project / ".env.production").write_text("TOKEN=secret\n")
    (project / ".envrc").write_text("export TOKEN=secret\n")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("secret")
    (project / ".fastmcp").mkdir()
    (project / ".fastmcp" / "project.json").write_text("secret")
    (project / ".venv").mkdir()
    (project / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (project / ".venv" / "secret.txt").write_text("secret")
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "server.pyc").write_bytes(b"cache")
    (project / "production.fastmcp.json").write_text(
        json.dumps({"deployment": {"env": {"TOKEN": "secret"}}})
    )

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    names = archive_names(bundle.archive_path)
    assert {
        "server.py",
        ".gitignore",
        "app/.gitignore",
        "app/keep.txt",
        "app/env",
        "app/env/settings.py",
    } <= names
    assert "keep.txt" not in names
    assert "ignored.txt" not in names
    assert not any(name.startswith(".env") for name in names)
    assert not any(name.startswith(".git/") for name in names)
    assert not any(name.startswith(".fastmcp/") for name in names)
    assert not any(name.startswith(".venv/") for name in names)
    assert not any("__pycache__" in name for name in names)
    assert "production.fastmcp.json" not in names


async def test_archive_preserves_empty_directories(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "data" / "uploads").mkdir(parents=True)

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    with tarfile.open(bundle.archive_path, "r:gz") as archive:
        data = archive.getmember("data")
        uploads = archive.getmember("data/uploads")
        assert data.isdir()
        assert uploads.isdir()
        assert uploads.mode == 0o755
        assert uploads.mtime == 0


@pytest.mark.parametrize(
    ("ignored_path", "pattern"),
    [
        ("src/server.py", "src/\n"),
        ("requirements.txt", "requirements.txt\n"),
    ],
)
async def test_required_ignored_path_is_rejected(
    project: Path,
    tmp_path: Path,
    ignored_path: str,
    pattern: str,
) -> None:
    write_server(project / "src" / "server.py")
    (project / "requirements.txt").write_text("fastmcp>=4\n")
    (project / ".gitignore").write_text(pattern)

    with pytest.raises(SourceInvalidError, match="Required source"):
        await create_source_bundle(
            "src/server.py",
            tmp_path / f"{Path(ignored_path).name}.tar.gz",
        )


async def test_parent_ignored_generated_dependency_path_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    project = repository / "service"
    write_server(project / "server.py")
    (repository / ".git").mkdir()
    (repository / ".gitignore").write_text("service/.fastmcp-deploy-requirements.txt\n")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"dependencies": ["httpx>=0.27"]},
            }
        )
    )
    monkeypatch.chdir(project)

    with pytest.raises(
        SourceInvalidError, match="generated dependency path is ignored"
    ):
        await create_source_bundle(None, tmp_path / "source.tar.gz")


async def test_ignored_generated_dependency_path_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / ".gitignore").write_text(".fastmcp-deploy-requirements.txt\n")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"dependencies": ["httpx>=0.27"]},
            }
        )
    )

    with pytest.raises(
        SourceInvalidError, match="generated dependency path is ignored"
    ):
        await create_source_bundle(None, tmp_path / "source.tar.gz")


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


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs extra access")
async def test_external_symlink_is_rejected(project: Path, tmp_path: Path) -> None:
    write_server(project / "server.py")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (project / "outside-link").symlink_to(outside)

    with pytest.raises(SourceInvalidError, match="Symbolic link leaves"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs extra access")
async def test_server_below_internal_directory_symlink_is_archived(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "real" / "server.py")
    (project / "pyproject.toml").write_text("[project]\nname = 'test'\nversion = '0'\n")
    (project / "linked").symlink_to(project / "real", target_is_directory=True)

    bundle = await create_source_bundle(
        "linked/server.py",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "linked/server.py:mcp"
    assert {"linked", "real", "real/server.py"} <= archive_names(bundle.archive_path)


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs extra access")
async def test_marker_free_symlinked_server_uses_resolved_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = tmp_path / "container"
    write_server(container / "real" / "server.py")
    (container / "unrelated-secret.txt").write_text("secret")
    (container / "linked").symlink_to(
        container / "real",
        target_is_directory=True,
    )
    monkeypatch.chdir(container)

    bundle = await create_source_bundle(
        "linked/server.py",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "server.py:mcp"
    assert archive_names(bundle.archive_path) == {"server.py"}


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs extra access")
async def test_marker_free_file_symlink_uses_target_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = tmp_path / "container"
    target = container / "real"
    write_server(target / "server.py")
    (target / "requirements.txt").write_text("fastmcp>=4\n")
    (container / "unrelated-secret.txt").write_text("secret")
    (container / "server-link.py").symlink_to(target / "server.py")
    monkeypatch.chdir(container)

    bundle = await create_source_bundle(
        "server-link.py",
        tmp_path / "source.tar.gz",
    )

    assert bundle.entrypoint == "server.py:mcp"
    assert bundle.dependency_path == "requirements.txt"
    assert archive_names(bundle.archive_path) == {"requirements.txt", "server.py"}


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs extra access")
async def test_internal_symlink_is_relative_in_archive(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "data.txt").write_text("data")
    (project / "data-link").symlink_to(project / "data.txt")

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    with tarfile.open(bundle.archive_path, "r:gz") as archive:
        link = archive.getmember("data-link")
        assert link.issym()
        assert link.linkname == "data.txt"


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs extra access")
async def test_symlink_to_ignored_target_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / ".gitignore").write_text("private.txt\n")
    (project / "private.txt").write_text("private")
    (project / "data-link").symlink_to(project / "private.txt")

    with pytest.raises(SourceInvalidError, match="target is not archived: data-link"):
        await create_source_bundle("server.py", tmp_path / "source.tar.gz")


async def test_archive_path_inside_source_root_is_rejected(project: Path) -> None:
    write_server(project / "server.py")

    with pytest.raises(SourceInvalidError, match="outside the source root"):
        await create_source_bundle("server.py", project / "source.tar.gz")


async def test_existing_archive_path_is_preserved(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    archive_path = tmp_path / "source.tar.gz"
    archive_path.write_bytes(b"existing")

    with pytest.raises(SourceInvalidError, match="already exists"):
        await create_source_bundle("server.py", archive_path)

    assert archive_path.read_bytes() == b"existing"


async def test_competing_archive_file_is_preserved(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_server(project / "server.py")
    archive_path = tmp_path / "source.tar.gz"
    original_collect_entries = source_bundle_module._collect_entries

    def create_competing_file(
        source_root: Path,
        *,
        required_paths: tuple[Path, ...],
        excluded_paths: tuple[Path, ...],
    ) -> list[tuple[str, Path | bytes]]:
        entries = original_collect_entries(
            source_root,
            required_paths=required_paths,
            excluded_paths=excluded_paths,
        )
        archive_path.write_bytes(b"competing")
        return entries

    monkeypatch.setattr(
        source_bundle_module,
        "_collect_entries",
        create_competing_file,
    )

    with pytest.raises(SourceInvalidError, match="already exists"):
        await create_source_bundle("server.py", archive_path)

    assert archive_path.read_bytes() == b"competing"


async def test_external_inline_dependency_path_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (tmp_path / "shared").mkdir()
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"dependencies": ["shared @ file:../shared"]},
            }
        )
    )

    with pytest.raises(SourceInvalidError, match="leaves the source root"):
        await create_source_bundle(None, tmp_path / "source.tar.gz")


async def test_invalid_inline_dependency_is_rejected(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {"dependencies": ["not a requirement"]},
            }
        )
    )

    with pytest.raises(SourceInvalidError, match="valid PEP 508 requirement"):
        await create_source_bundle(None, tmp_path / "source.tar.gz")


async def test_archive_size_limit_uses_compressed_size(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_server(project / "server.py")
    (project / "data.bin").write_bytes(os.urandom(1024 * 1024))
    (project / "z-after-limit.txt").write_text("not reached")
    archive_path = tmp_path / "source.tar.gz"
    visited: list[str] = []
    original_add_entry = source_archive_module._add_archive_entry

    def record_entry(
        archive: tarfile.TarFile,
        name: str,
        entry_source: Path | bytes,
        source_root: Path,
    ) -> None:
        visited.append(name)
        original_add_entry(archive, name, entry_source, source_root)

    monkeypatch.setattr(source_archive_module, "MAX_SOURCE_UPLOAD_BYTES", 100)
    monkeypatch.setattr(source_archive_module, "_add_archive_entry", record_entry)

    with pytest.raises(ArchiveTooLargeError, match="250 MB"):
        await create_source_bundle("server.py", archive_path)

    assert "z-after-limit.txt" not in visited
    assert not archive_path.exists()
