from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

import pytest

from fastmcp.cli.deploy.source_bundle import SourceInvalidError, create_source_bundle
from fastmcp.cli.deploy.source_dependencies import GENERATED_REQUIREMENTS_PATH


def write_server(path: Path, name: str = "mcp") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from fastmcp import FastMCP\n"
        f'{name} = FastMCP("Test")\n'
        f"@{name}.tool\n"
        "def ping() -> str:\n"
        '    return "pong"\n'
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source_root = tmp_path / "project"
    source_root.mkdir()
    monkeypatch.chdir(source_root)
    return source_root


def archive_names(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as archive:
        return {member.name for member in archive.getmembers()}


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

    assert bundle.entrypoint == "src/server.py"
    assert bundle.dependency_path == "requirements.txt"
    assert bundle.size_bytes == bundle.archive_path.stat().st_size
    assert len(bundle.checksum_sha256) == 64
    assert {"src/server.py", "requirements.txt"} <= archive_names(bundle.archive_path)


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

    assert bundle.entrypoint == "src/server.py"
    assert bundle.dependency_path == "src/requirements.txt"


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

    assert bundle.entrypoint == "server.py"
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


@pytest.mark.parametrize(
    "requirements_name",
    ["requirements'prod.txt", "requirements\\prod.txt"],
)
async def test_generated_requirements_rejects_unsafe_include_path(
    project: Path,
    tmp_path: Path,
    requirements_name: str,
) -> None:
    if os.name == "nt" and "\\" in requirements_name:
        pytest.skip("A backslash is a path separator on Windows")

    write_server(project / "server.py")
    (project / requirements_name).write_text("fastmcp>=4\n")
    (project / "fastmcp.json").write_text(
        json.dumps(
            {
                "source": {"path": "server.py"},
                "environment": {
                    "requirements": requirements_name,
                    "dependencies": ["httpx>=0.27"],
                },
            }
        )
    )

    with pytest.raises(SourceInvalidError, match="unsupported characters"):
        await create_source_bundle(None, tmp_path / "source.tar.gz")


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


async def test_detected_uv_project_uses_lock_file(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "src" / "server.py")
    (project / "pyproject.toml").write_text('[project]\nname = "project"\n')
    (project / "uv.lock").write_text("version = 1\n")

    bundle = await create_source_bundle("src/server.py", tmp_path / "source.tar.gz")

    assert bundle.dependency_path == "uv.lock"


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


async def test_parent_ignore_does_not_remove_generated_dependency(
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

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert GENERATED_REQUIREMENTS_PATH in archive_names(bundle.archive_path)


async def test_root_ignore_does_not_remove_generated_dependency(
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

    bundle = await create_source_bundle(None, tmp_path / "source.tar.gz")

    assert GENERATED_REQUIREMENTS_PATH in archive_names(bundle.archive_path)


async def test_requirements_contents_are_validated_by_horizon(
    project: Path,
    tmp_path: Path,
) -> None:
    write_server(project / "server.py")
    (project / "requirements.txt").write_text("-r ../outside.txt\n")
    (tmp_path / "outside.txt").write_text("httpx\n")

    bundle = await create_source_bundle("server.py", tmp_path / "source.tar.gz")

    assert bundle.dependency_path == "requirements.txt"
    assert "requirements.txt" in archive_names(bundle.archive_path)


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
