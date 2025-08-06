"""FastMCP CLI tools using Cyclopts."""

import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal

import cyclopts
import pyperclip
from pydantic import BaseModel, Field, TypeAdapter
from rich.console import Console
from rich.table import Table

import fastmcp
from fastmcp.cli import run as run_module
from fastmcp.cli.install import install_app
from fastmcp.client.client import Client
from fastmcp.client.transports import (
    FastMCPTransport,
    NodeStdioTransport,
    PythonStdioTransport,
    SSETransport,
    StreamableHttpTransport,
    UvStdioTransport,
)
from fastmcp.server.proxy import FastMCPProxy
from fastmcp.server.server import FastMCP
from fastmcp.utilities.inspect import FastMCPInfo, inspect_fastmcp
from fastmcp.utilities.logging import get_logger

logger = get_logger("cli")
console = Console()

app = cyclopts.App(
    name="fastmcp",
    help="FastMCP 2.0 - The fast, Pythonic way to build MCP servers and clients.",
    version=fastmcp.__version__,
)

list_app = cyclopts.App(
    name="list",
)
app.command(list_app)

call_app = cyclopts.App(
    name="call",
)
app.command(call_app)


class StdioSettings(BaseModel):
    def run_server(self, server: FastMCP) -> None:
        server.run()


class HttpSettings(BaseModel):
    transport: Literal["http", "sse", "streamable-http"] = Field(default="http")
    host: str | None = Field(default=None)
    port: int | None = Field(default=None)
    path: str | None = Field(default=None)
    no_banner: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = Field(
        default=None
    )

    def run_server(self, server: FastMCP) -> None:
        server.run(
            transport=self.transport,
            host=self.host,
            port=self.port,
            path=self.path,
            log_level=self.log_level,
        )


class InspectableCliServer(BaseModel):
    server_spec: str

    @staticmethod
    def is_url(path: str) -> bool:
        """Check if a string is a URL."""
        url_pattern = re.compile(r"^https?://")
        return bool(url_pattern.match(path))

    @property
    def path_and_server_object(self) -> tuple[Path, str | None]:
        """Parse a file path that may include a server object specification.

        Args:
            server_spec: Path to file, optionally with :object suffix

        Returns:
            Tuple of (file_path, server_object)
        """
        # First check if we have a Windows path (e.g., C:\...)
        has_windows_drive = len(self.server_spec) > 1 and self.server_spec[1] == ":"

        # Split on the last colon, but only if it's not part of the Windows drive letter
        # and there's actually another colon in the string after the drive letter
        if ":" in (self.server_spec[2:] if has_windows_drive else self.server_spec):
            file_str, server_object = self.server_spec.rsplit(":", 1)
        else:
            file_str, server_object = self.server_spec, None

        # Resolve the file path
        file_path = Path(file_str).expanduser().resolve()
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        if not file_path.is_file():
            logger.error(f"Not a file: {file_path}")
            sys.exit(1)

        return file_path, server_object

    @property
    def server_should_use_remote_client(self) -> bool:
        return self.is_url(self.server_spec)

    @property
    def server_should_use_mcp_config(self) -> bool:
        return self.server_spec.endswith(".json")

    @property
    def server_should_use_direct_import(self) -> bool:
        return not any(
            [self.server_should_use_remote_client, self.server_should_use_mcp_config]
        )


class CliServer(InspectableCliServer):
    server_args: list[str] = Field(default_factory=list)

    def build_server_with_mcp_config(self) -> FastMCP:
        mcp_config_path = Path(self.server_spec)
        with mcp_config_path.open() as src:
            mcp_config = json.load(src)

        server = FastMCP.as_proxy(mcp_config)
        return server

    def build_server_with_remote_client(self) -> FastMCP:
        client: Client[
            PythonStdioTransport
            | NodeStdioTransport
            | SSETransport
            | StreamableHttpTransport
        ] = fastmcp.Client(self.server_spec)
        server: FastMCPProxy = fastmcp.FastMCP.from_client(client)
        return server

    def build_server_with_direct_import(self) -> FastMCP:
        file, server_object = self.path_and_server_object
        server = run_module.import_server_with_args(
            file, server_object, self.server_args
        )
        return server

    @property
    def server(self) -> FastMCP:
        if self.server_should_use_remote_client:
            return self.build_server_with_remote_client()
        elif self.server_should_use_mcp_config:
            return self.build_server_with_mcp_config()
        else:
            return self.build_server_with_direct_import()

    @property
    def transport(self) -> FastMCPTransport:
        return FastMCPTransport(mcp=self.server)

    @property
    def client(self) -> Client:
        return Client(transport=self.transport)


class UvCliServer(CliServer):
    python: str | None = Field(default=None)
    with_packages: list[str] = Field(default_factory=list)
    project: Path | None = Field(default=None)
    with_requirements: Path | None = Field(default=None)
    transport_settings: Annotated[
        HttpSettings | StdioSettings, cyclopts.Parameter(name="*")
    ] = Field(default=StdioSettings())

    @property
    def transport(self) -> UvStdioTransport:
        return UvStdioTransport(
            command=self.server_spec,
            args=["--with", "fastmcp", *self.server_args],
            with_packages=self.with_packages,
            with_requirements=self.with_requirements,
            project_directory=self.project,
            python_version=self.python,
            env_vars=os.environ.copy(),
        )

    def command(self) -> str:
        return self.transport.to_cli()


class RunnableCliServer(CliServer):
    transport_settings: Annotated[
        HttpSettings | StdioSettings, cyclopts.Parameter(name="*")
    ] = Field(default=StdioSettings())

    def run_server(self) -> None:
        self.transport_settings.run_server(server=self.server)


class RunnableUvCliServer(UvCliServer):
    transport_settings: Annotated[
        HttpSettings | StdioSettings, cyclopts.Parameter(name="*")
    ] = Field(default=StdioSettings())

    def run_server(self) -> None:
        self.transport_settings.run_server(server=self.server)


class InspectorCliServer(UvCliServer):
    inspector_version: str | None = Field(default=None)
    ui_port: int | None = Field(default=None)
    server_port: int | None = Field(default=None)

    @classmethod
    def _get_npx_command(cls) -> str:
        """Get the correct npx command for the current platform."""
        if sys.platform == "win32":
            # Try both npx.cmd and npx.exe on Windows
            for cmd in ["npx.cmd", "npx.exe", "npx"]:
                try:
                    subprocess.run(
                        [cmd, "--version"], check=True, capture_output=True, shell=True
                    )
                    return cmd
                except subprocess.CalledProcessError:
                    continue
            raise FileNotFoundError("npx not found")
        return "npx"  # On Unix-like systems, just use npx

    def to_env_vars(self) -> dict[str, str]:
        return {
            "CLIENT_PORT": str(self.ui_port),
            "SERVER_PORT": str(self.server_port),
        }

    def to_inspector_command(self) -> str:
        return f"{self._get_npx_command()} @modelcontextprotocol/inspector@{self.inspector_version}"


@app.command
def version(
    *,
    copy: Annotated[
        bool,
        cyclopts.Parameter(
            "--copy",
            help="Copy version information to clipboard",
            negative=False,
        ),
    ] = False,
):
    """Display version information and platform details."""
    info = {
        "FastMCP version": fastmcp.__version__,
        "MCP version": importlib.metadata.version("mcp"),
        "Python version": platform.python_version(),
        "Platform": platform.platform(),
        "FastMCP root path": Path(fastmcp.__file__).resolve().parents[1],
    }

    g = Table.grid(padding=(0, 1))
    g.add_column(style="bold", justify="left")
    g.add_column(style="cyan", justify="right")
    for k, v in info.items():
        g.add_row(k + ":", str(v).replace("\n", " "))

    if copy:
        # Use Rich's plain text rendering for copying
        plain_console = Console(file=None, force_terminal=False, legacy_windows=False)
        with plain_console.capture() as capture:
            plain_console.print(g)
        pyperclip.copy(capture.get())
        console.print("[green]✓[/green] Version information copied to clipboard")
    else:
        console.print(g)


@app.command
def dev(
    inspector_cli_server: Annotated[InspectorCliServer, cyclopts.Parameter(name="*")],
) -> None:
    """Run an MCP server with the MCP Inspector for development.

    Args:
        server_spec: Python file to run, optionally with :object suffix
    """
    inspector_cmd = inspector_cli_server.to_inspector_command()

    uv_cmd = inspector_cli_server.transport.to_cli()

    try:
        shell = sys.platform == "win32"
        process = subprocess.run(
            [inspector_cmd, uv_cmd],
            check=True,
            shell=shell,
            env=dict(os.environ.items()) | inspector_cli_server.to_env_vars(),
        )
        sys.exit(process.returncode)
    except subprocess.CalledProcessError as e:
        logger.error(
            "Dev server failed",
            extra={
                "file": str(inspector_cli_server.server_spec),
                "error": str(e),
                "returncode": e.returncode,
            },
        )
        sys.exit(e.returncode)
    except FileNotFoundError:
        logger.error(
            "npx not found. Please ensure Node.js and npm are properly installed "
            "and added to your system PATH. You may need to restart your terminal "
            "after installation.",
            extra={"file": str(inspector_cli_server.server_spec)},
        )
        sys.exit(1)


@app.command
def run(
    cli_server: Annotated[
        RunnableUvCliServer | RunnableCliServer, cyclopts.Parameter(name="*")
    ],
    *server_args: str,
) -> None:
    """Run an MCP server or connect to a remote one.

    The server can be specified in four ways:
    1. Module approach: "server.py" - runs the module directly, looking for an object named 'mcp', 'server', or 'app'
    2. Import approach: "server.py:app" - imports and runs the specified server object
    3. URL approach: "http://server-url" - connects to a remote server and creates a proxy
    4. MCPConfig file: "mcp.json" - runs as a proxy server for the MCP Servers in the MCPConfig file

    Server arguments can be passed after -- :
    fastmcp run server.py -- --config config.json --debug

    Args:
        server_spec: Python file, object specification (file:obj), MCPConfig file, or URL
    """

    cli_server.server_args.extend(server_args)

    cli_server.run_server()


@list_app.command(name="tools")
async def list_tools(
    cli_server: Annotated[UvCliServer | CliServer, cyclopts.Parameter(name="*")],
    *server_args: str,
) -> None:
    """List tools on the server."""

    cli_server.server_args.extend(server_args)

    async with cli_server.client as client:
        tools = await client.list_tools()

        for tool in tools:
            console.print(f"{tool.name}: {tool.description}")

        await client.close()


@list_app.command(name="resources")
async def list_resources(
    cli_server: Annotated[UvCliServer | CliServer, cyclopts.Parameter(name="*")],
    *server_args: str,
) -> None:
    """List resources on the server."""

    cli_server.server_args.extend(server_args)

    async with cli_server.client as client:
        resources = await client.list_resources()

        for resource in resources:
            console.print(f"{resource.name}: {resource.description}")

        await client.close()


@list_app.command(name="prompts")
async def list_prompts(
    cli_server: Annotated[UvCliServer | CliServer, cyclopts.Parameter(name="*")],
    *server_args: str,
) -> None:
    """List prompts on the server."""

    cli_server.server_args.extend(server_args)

    async with cli_server.client as client:
        prompts = await client.list_prompts()

        for prompt in prompts:
            console.print(f"{prompt.name}: {prompt.description}")

        await client.close()


# @list_app.command(name="tools")
# async def call_tools(
#     cli_server: Annotated[
#         UvCliServer | CliServer, cyclopts.Parameter(name="*")
#     ],
#     tool: str,
#     json_args: str | None = None,
#     *server_args: str,
# ) -> None:
#     """List tools on the server."""

#     cli_server.server_args.extend(server_args)

#     async with cli_server.client:
#         tools = await cli_server.client.list_tools()

#         args = json.loads(json_args) if json_args else {}

#         result = await cli_server.client.call_tool(tool, args)

#         console.print(result)


@app.command
async def inspect(
    cli_server: Annotated[InspectableCliServer, cyclopts.Parameter(name="*")],
    *,
    output: Annotated[
        Path,
        cyclopts.Parameter(
            name=["--output", "-o"],
            help="Output file path for the JSON report (default: server-info.json)",
        ),
    ] = Path("server-info.json"),
) -> None:
    """Inspect an MCP server and generate a JSON report.

    This command analyzes an MCP server and generates a comprehensive JSON report
    containing information about the server's name, instructions, version, tools,
    prompts, resources, templates, and capabilities.

    Examples:
        fastmcp inspect server.py
        fastmcp inspect server.py -o report.json
        fastmcp inspect server.py:mcp -o analysis.json
        fastmcp inspect path/to/server.py:app -o /tmp/server-info.json

    Args:
        server_spec: Python file to inspect, optionally with :object suffix
    """
    # Parse the server specification

    inspectable_server: InspectableCliServer = InspectableCliServer(
        server_spec=cli_server.server_spec
    )

    file_path, server_object = inspectable_server.path_and_server_object

    logger.debug(
        "Inspecting server",
        extra={
            "file": str(file_path),
            "server_object": server_object,
            "output": str(output),
        },
    )

    try:
        # Import the server
        server = run_module.import_server(file_path, server_object)

        # Get server information - using native async support
        info = await inspect_fastmcp(server)

        info_json = TypeAdapter(FastMCPInfo).dump_json(info, indent=2)

        # Ensure output directory exists
        output.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON report (always pretty-printed)
        with output.open("w", encoding="utf-8") as f:
            f.write(info_json.decode("utf-8"))

        logger.info(f"Server inspection complete. Report saved to {output}")

        # Print summary to console
        console.print(
            f"[bold green]✓[/bold green] Inspected server: [bold]{info.name}[/bold]"
        )
        console.print(f"  Tools: {len(info.tools)}")
        console.print(f"  Prompts: {len(info.prompts)}")
        console.print(f"  Resources: {len(info.resources)}")
        console.print(f"  Templates: {len(info.templates)}")
        console.print(f"  Report saved to: [cyan]{output}[/cyan]")

    except Exception as e:
        logger.error(
            f"Failed to inspect server: {e}",
            extra={
                "server_spec": cli_server.server_spec,
                "error": str(e),
            },
        )
        console.print(f"[bold red]✗[/bold red] Failed to inspect server: {e}")
        sys.exit(1)


# Add install subcommands using proper Cyclopts pattern
app.command(install_app)


if __name__ == "__main__":
    app()
