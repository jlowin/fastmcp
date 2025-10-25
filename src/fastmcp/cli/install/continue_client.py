"""Continue integration for FastMCP install using Cyclopts."""

import sys
from pathlib import Path
from typing import Annotated, Any

import cyclopts
import yaml
from rich import print

from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.mcp_server_config.v1.environments.uv import UVEnvironment

from .shared import process_common_args

logger = get_logger(__name__)


def get_continue_mcp_servers_dir() -> Path:
    """Get the platform-agnostic Continue mcpServers directory.

    Returns:
        Path to the global ~/.continue/mcpServers directory
    """
    home = Path.home()
    return home / ".continue" / "mcpServers"


def convert_env_to_continue_format(
    env_vars: dict[str, str] | None,
) -> dict[str, str] | None:
    """Convert environment variables to Continue's YAML format.

    Continue stores actual environment variable values directly in the YAML.
    Returns None for empty dict to match Continue's schema.
    """
    if not env_vars:
        return None
    return env_vars


def install_continue(
    file: Path,
    server_object: str | None,
    name: str,
    *,
    with_editable: list[Path] | None = None,
    with_packages: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    python_version: str | None = None,
    with_requirements: Path | None = None,
    project: Path | None = None,
) -> bool:
    """Install FastMCP server in Continue.

    Args:
        file: Path to the server file
        server_object: Optional server object name (for :object suffix)
        name: Name for the server in Continue
        with_editable: Optional list of directories to install in editable mode
        with_packages: Optional list of additional packages to install
        env_vars: Optional dictionary of environment variables
        python_version: Optional Python version to use
        with_requirements: Optional requirements file to install from
        project: Optional project directory to run within

    Returns:
        True if installation was successful, False otherwise
    """
    mcp_servers_dir = get_continue_mcp_servers_dir()
    mcp_servers_dir.mkdir(parents=True, exist_ok=True)
    config_file = mcp_servers_dir / f"{name}.yaml"

    env_config = UVEnvironment(
        python=python_version,
        dependencies=(with_packages or []) + ["fastmcp"],
        requirements=with_requirements,
        project=project,
        editable=with_editable,
    )

    if server_object:
        server_spec = f"{file.resolve()}:{server_object}"
    else:
        server_spec = str(file.resolve())

    full_command = env_config.build_command(["fastmcp", "run", server_spec])

    server_config: dict[str, Any] = {
        "name": name,
        "type": "stdio",
        "command": full_command[0],
    }

    if len(full_command) > 1:
        server_config["args"] = full_command[1:]

    if env_vars:
        server_config["env"] = convert_env_to_continue_format(env_vars)

    if project:
        server_config["cwd"] = str(project)

    # Continue requires block schema format with mcpServers array even for individual files
    block_config: dict[str, Any] = {
        "name": name,
        "version": "0.0.1",
        "schema": "v1",
        "mcpServers": [server_config],
    }

    try:
        with open(config_file, "w") as f:
            yaml.dump(block_config, f, default_flow_style=False, sort_keys=False)

        print(
            f"[green]Successfully installed '{name}' to Continue[/green]\n"
            f"[blue]Config file: {config_file}[/blue]"
        )
        return True
    except Exception as e:
        print(f"[red]Failed to install server: {e}[/red]")
        return False


async def continue_command(
    server_spec: str,
    *,
    server_name: Annotated[
        str | None,
        cyclopts.Parameter(
            name=["--name", "-n"],
            help="Custom name for the server in Continue",
        ),
    ] = None,
    with_editable: Annotated[
        list[Path] | None,
        cyclopts.Parameter(
            "--with-editable",
            help="Directory with pyproject.toml to install in editable mode (can be used multiple times)",
            negative="",
        ),
    ] = None,
    with_packages: Annotated[
        list[str] | None,
        cyclopts.Parameter(
            "--with",
            help="Additional packages to install (can be used multiple times)",
            negative="",
        ),
    ] = None,
    env_vars: Annotated[
        list[str] | None,
        cyclopts.Parameter(
            "--env",
            help="Environment variables in KEY=VALUE format (can be used multiple times)",
            negative="",
        ),
    ] = None,
    env_file: Annotated[
        Path | None,
        cyclopts.Parameter(
            "--env-file",
            help="Load environment variables from .env file",
        ),
    ] = None,
    python: Annotated[
        str | None,
        cyclopts.Parameter(
            "--python",
            help="Python version to use (e.g., 3.10, 3.11)",
        ),
    ] = None,
    with_requirements: Annotated[
        Path | None,
        cyclopts.Parameter(
            "--with-requirements",
            help="Requirements file to install dependencies from",
        ),
    ] = None,
    project: Annotated[
        Path | None,
        cyclopts.Parameter(
            "--project",
            help="Run the command within the given project directory",
        ),
    ] = None,
) -> None:
    """Install an MCP server in Continue.

    Args:
        server_spec: Python file to install, optionally with :object suffix
    """
    with_editable = with_editable or []
    with_packages = with_packages or []
    env_vars = env_vars or []
    file, server_object, name, with_packages, env_dict = await process_common_args(
        server_spec, server_name, with_packages, env_vars, env_file
    )

    success = install_continue(
        file=file,
        server_object=server_object,
        name=name,
        with_editable=with_editable,
        with_packages=with_packages,
        env_vars=env_dict,
        python_version=python,
        with_requirements=with_requirements,
        project=project,
    )

    if not success:
        sys.exit(1)
