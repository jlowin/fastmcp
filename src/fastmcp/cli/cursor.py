"""Cursor app integration utilities."""

import json
import os
import sys
import subprocess
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


def get_cursor_config_path() -> Path | None:
    """Get the Cursor config directory based on platform."""
    # Cursor stores its MCP config in ~/.cursor/mcp.json across all platforms
    cursor_dir = Path.home() / ".cursor"
    
    if cursor_dir.exists():
        return cursor_dir
    return None


def open_cursor_deeplink(server_name: str) -> bool:
    """Open Cursor with a deeplink to highlight the MCP server configuration.
    
    Args:
        server_name: Name of the server that was just installed
        
    Returns:
        True if the deeplink was opened successfully, False otherwise
    """
    try:
        # Cursor deeplink format for opening settings
        # This is a hypothetical format - actual format may differ
        deeplink = f"cursor://settings/mcp?highlight={quote(server_name)}"
        
        logger.debug(f"Opening Cursor deeplink: {deeplink}")
        
        # Try to open the deeplink
        if sys.platform == "darwin":  # macOS
            subprocess.run(["open", deeplink], check=True)
        elif sys.platform == "win32":  # Windows
            os.startfile(deeplink)
        else:  # Linux and others
            webbrowser.open(deeplink)
            
        return True
    except Exception as e:
        logger.debug(f"Failed to open Cursor deeplink: {e}")
        return False


def update_cursor_config(
    file_spec: str,
    server_name: str,
    *,
    with_editable: Path | None = None,
    with_packages: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    transport: str = "stdio",  # Default to stdio transport
    open_cursor: bool = True,  # Whether to open Cursor after installation
) -> bool:
    """Add or update a FastMCP server in Cursor's configuration.

    Args:
        file_spec: Path to the server file, optionally with :object suffix
        server_name: Name for the server in Cursor's config
        with_editable: Optional directory to install in editable mode
        with_packages: Optional list of additional packages to install
        env_vars: Optional dictionary of environment variables. These are merged with
            any existing variables, with new values taking precedence.
        transport: Transport type to use (stdio or sse)
        open_cursor: Whether to open Cursor after installation

    Raises:
        RuntimeError: If Cursor's config directory is not found, indicating
            Cursor may not be installed or properly set up.
    """
    config_dir = get_cursor_config_path()
    if not config_dir:
        raise RuntimeError(
            "Cursor config directory not found. Please ensure Cursor"
            " is installed and has been run at least once to initialize its config."
        )

    config_file = config_dir / "mcp.json"
    if not config_file.exists():
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text("{}")
        except Exception as e:
            logger.error(
                "Failed to create Cursor MCP config file",
                extra={
                    "error": str(e),
                    "config_file": str(config_file),
                },
            )
            return False

    try:
        config = json.loads(config_file.read_text())
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        # Check if server already exists
        is_update = server_name in config["mcpServers"]

        # Always preserve existing env vars and merge with new ones
        if is_update and "env" in config["mcpServers"][server_name]:
            existing_env = config["mcpServers"][server_name]["env"]
            if env_vars:
                # New vars take precedence over existing ones
                env_vars = {**existing_env, **env_vars}
            else:
                env_vars = existing_env

        # Cursor supports both stdio and SSE transport
        if transport == "sse":
            # For SSE transport, we need to provide a URL
            # This would typically be for remote servers
            server_config: dict[str, Any] = {
                "url": f"http://localhost:8000/sse"  # Default SSE endpoint
            }
            if env_vars:
                server_config["env"] = env_vars
        else:
            # Default to stdio transport with command execution
            # Build uv run command
            args = ["run"]

            # Collect all packages in a set to deduplicate
            packages = {"fastmcp"}
            if with_packages:
                packages.update(pkg for pkg in with_packages if pkg)

            # Add all packages with --with
            for pkg in sorted(packages):
                args.extend(["--with", pkg])

            if with_editable:
                args.extend(["--with-editable", str(with_editable)])

            # Convert file path to absolute before adding to command
            # Split off any :object suffix first
            if ":" in file_spec:
                file_path, server_object = file_spec.rsplit(":", 1)
                file_spec = f"{Path(file_path).resolve()}:{server_object}"
            else:
                file_spec = str(Path(file_spec).resolve())

            # Add fastmcp run command
            args.extend(["fastmcp", "run", file_spec])

            server_config = {
                "command": "uv",
                "args": args
            }

            # Add environment variables if specified
            if env_vars:
                server_config["env"] = env_vars

        config["mcpServers"][server_name] = server_config

        config_file.write_text(json.dumps(config, indent=2))
        
        action = "Updated" if is_update else "Added"
        logger.info(
            f"{action} server '{server_name}' in Cursor config",
            extra={"config_file": str(config_file)},
        )
        
        # Try to open Cursor with deeplink if requested
        if open_cursor:
            if open_cursor_deeplink(server_name):
                logger.info("Opened Cursor to highlight the new MCP server")
            else:
                logger.info(
                    f"Please restart Cursor to use the {server_name} MCP server"
                )
        
        return True
    except Exception as e:
        logger.error(
            "Failed to update Cursor config",
            extra={
                "error": str(e),
                "config_file": str(config_file),
            },
        )
        return False


def list_cursor_servers() -> dict[str, Any] | None:
    """List all MCP servers configured in Cursor.
    
    Returns:
        Dictionary of configured servers or None if config not found
    """
    config_dir = get_cursor_config_path()
    if not config_dir:
        return None
        
    config_file = config_dir / "mcp.json"
    if not config_file.exists():
        return {}
        
    try:
        config = json.loads(config_file.read_text())
        return config.get("mcpServers", {})
    except Exception as e:
        logger.error(f"Failed to read Cursor config: {e}")
        return None 