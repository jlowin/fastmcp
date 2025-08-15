"""FastMCP server configuration management.

This module provides configuration schema and utilities for fastmcp.json files,
enabling structured server configuration with dependencies, transport settings,
and runtime parameters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FastMCPServerConfig(BaseModel):
    """Configuration for a single FastMCP server instance.
    
    This configuration can be loaded from a fastmcp.json file to specify
    server settings, dependencies, and runtime parameters.
    """
    
    # Server identification
    name: str | None = None
    version: str = "1.0.0"
    
    # Entry point specification
    # Examples: "server.py", "server.py:mcp", "myapp.server:create_server()"
    entrypoint: str
    
    # Dependencies
    dependencies: list[str] = Field(
        default_factory=list,
        description="Python packages required by this server"
    )
    python_version: str | None = Field(
        default=None,
        description="Python version constraint (e.g., '3.10', '>=3.10,<3.12')"
    )
    requirements_file: str | None = Field(
        default=None,
        description="Path to requirements.txt file"
    )
    
    # Transport configuration
    transport: Literal["stdio", "http", "sse", "streamable-http"] = Field(
        default="stdio",
        description="Transport protocol to use"
    )
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind to (for HTTP transports)"
    )
    port: int = Field(
        default=8000,
        description="Port to bind to (for HTTP transports)"
    )
    path: str = Field(
        default="/mcp",
        description="Path to bind to (for HTTP transports)"
    )
    
    # Runtime configuration
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set"
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory for server execution"
    )
    timeout: int | None = Field(
        default=None,
        description="Maximum response time in milliseconds"
    )
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    
    # Server behavior
    show_banner: bool = Field(
        default=True,
        description="Whether to show the server banner on startup"
    )
    
    # Authentication (optional)
    auth_provider: str | None = Field(
        default=None,
        description="Authentication provider (e.g., 'bearer', 'jwt', 'workos')"
    )
    auth_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Authentication provider configuration"
    )
    
    # Metadata
    description: str | None = Field(
        default=None,
        description="Human-readable server description"
    )
    icon: str | None = Field(
        default=None,
        description="Icon path or URL for UI display"
    )
    
    model_config = ConfigDict(extra="allow")
    
    @field_validator("requirements_file")
    @classmethod
    def validate_requirements_file(cls, v: str | None) -> str | None:
        """Validate that requirements file exists if specified."""
        if v is not None:
            path = Path(v)
            if not path.exists():
                raise ValueError(f"Requirements file not found: {v}")
        return v
    
    def to_cli_args(self) -> list[str]:
        """Convert config to CLI arguments for the run command."""
        args = []
        
        # Add transport options
        if self.transport != "stdio":
            args.extend(["--transport", self.transport])
        if self.transport in ["http", "sse", "streamable-http"]:
            args.extend(["--host", self.host])
            args.extend(["--port", str(self.port)])
            args.extend(["--path", self.path])
        
        # Add log level
        if self.log_level != "INFO":
            args.extend(["--log-level", self.log_level])
        
        # Add banner flag
        if not self.show_banner:
            args.append("--no-banner")
        
        return args
    
    def get_dependencies_args(self) -> dict[str, Any]:
        """Get dependency-related arguments for uv run."""
        args = {}
        
        if self.dependencies:
            args["with_packages"] = self.dependencies
        
        if self.requirements_file:
            args["with_requirements"] = Path(self.requirements_file)
        
        if self.python_version:
            args["python_version"] = self.python_version
        
        return args


class FastMCPConfig(BaseModel):
    """Root configuration that can contain multiple servers."""
    
    # Single server mode (when no 'servers' key is present)
    # All FastMCPServerConfig fields are inherited here
    
    # Multi-server mode
    servers: dict[str, FastMCPServerConfig] | None = None
    
    # Default server to use when none specified
    default: str | None = None
    
    model_config = ConfigDict(extra="allow")
    
    @classmethod
    def from_file(cls, file_path: Path) -> FastMCPConfig | None:
        """Load configuration from a JSON file.
        
        Args:
            file_path: Path to the fastmcp.json file
            
        Returns:
            FastMCPConfig instance or None if file doesn't exist
        """
        if not file_path.exists():
            return None
        
        with file_path.open() as f:
            data = json.load(f)
        
        # Check if it's a multi-server config
        if "servers" in data:
            return cls(**data)
        else:
            # Single server config - wrap it
            return cls(servers={"default": FastMCPServerConfig(**data)}, default="default")
    
    def get_server_config(self, name: str | None = None) -> FastMCPServerConfig | None:
        """Get a specific server configuration.
        
        Args:
            name: Name of the server to get. If None, uses the default.
            
        Returns:
            Server configuration or None if not found
        """
        if self.servers is None:
            return None
        
        if name is None:
            name = self.default
        
        if name is None and len(self.servers) == 1:
            # If there's only one server and no default specified, use it
            name = next(iter(self.servers.keys()))
        
        if name is None:
            return None
        
        return self.servers.get(name)
    
    def write_to_file(self, file_path: Path) -> None:
        """Write configuration to a JSON file.
        
        Args:
            file_path: Path where to write the configuration
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # If single server mode, unwrap it for cleaner JSON
        if self.servers and len(self.servers) == 1 and self.default:
            data = self.servers[self.default].model_dump(exclude_none=True)
        else:
            data = self.model_dump(exclude_none=True)
        
        with file_path.open("w") as f:
            json.dump(data, f, indent=2)


def load_fastmcp_config(path: Path | str | None = None) -> FastMCPServerConfig | None:
    """Load FastMCP configuration from a file.
    
    Args:
        path: Path to config file. If None, looks for fastmcp.json in current directory.
        
    Returns:
        Server configuration or None if not found
    """
    if path is None:
        path = Path("fastmcp.json")
    elif isinstance(path, str):
        path = Path(path)
    
    config = FastMCPConfig.from_file(path)
    if config is None:
        return None
    
    return config.get_server_config()


def create_default_config(
    entrypoint: str = "server.py:mcp",
    name: str = "my-server",
    transport: str = "stdio"
) -> FastMCPServerConfig:
    """Create a default configuration.
    
    Args:
        entrypoint: Server entrypoint
        name: Server name
        transport: Transport type
        
    Returns:
        Default server configuration
    """
    return FastMCPServerConfig(
        name=name,
        entrypoint=entrypoint,
        transport=transport  # type: ignore
    )