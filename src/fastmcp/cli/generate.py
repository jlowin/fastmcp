"""Generate a standalone CLI script from an MCP server's capabilities."""

import re
import sys
import textwrap
from pathlib import Path
from typing import Annotated, Any

import cyclopts
import mcp.types
from mcp import McpError
from rich.console import Console

from fastmcp.cli.client import _build_client, resolve_server_spec
from fastmcp.client.transports.base import ClientTransport
from fastmcp.client.transports.stdio import StdioTransport
from fastmcp.utilities.logging import get_logger

logger = get_logger("cli.generate")
console = Console()

# ---------------------------------------------------------------------------
# JSON Schema type → Python type string
# ---------------------------------------------------------------------------

_JSON_SCHEMA_TYPE_MAP: dict[str, str] = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
    "null": "None",
}


def _schema_type_to_python(schema: dict[str, Any]) -> str:
    """Convert a JSON Schema type fragment to a Python type annotation string."""
    if "anyOf" in schema:
        parts = [_schema_type_to_python(s) for s in schema["anyOf"]]
        return " | ".join(parts)

    schema_type = schema.get("type", "string")
    if isinstance(schema_type, list):
        return " | ".join(_JSON_SCHEMA_TYPE_MAP.get(t, "str") for t in schema_type)

    return _JSON_SCHEMA_TYPE_MAP.get(schema_type, "str")


# ---------------------------------------------------------------------------
# Transport serialization
# ---------------------------------------------------------------------------


def serialize_transport(
    resolved: str | dict[str, Any] | ClientTransport,
) -> tuple[str, set[str]]:
    """Serialize a resolved transport to a Python expression string.

    Returns ``(expression, extra_imports)`` where *extra_imports* is a set of
    import lines needed by the expression.
    """
    if isinstance(resolved, str):
        return repr(resolved), set()

    if isinstance(resolved, StdioTransport):
        parts = [f"command={resolved.command!r}", f"args={resolved.args!r}"]
        if resolved.env:
            parts.append(f"env={resolved.env!r}")
        if resolved.cwd:
            parts.append(f"cwd={resolved.cwd!r}")
        expr = f"StdioTransport({', '.join(parts)})"
        imports = {"from fastmcp.client.transports import StdioTransport"}
        return expr, imports

    if isinstance(resolved, dict):
        return repr(resolved), set()

    # Fallback: try repr
    return repr(resolved), set()


# ---------------------------------------------------------------------------
# Per-tool code generation
# ---------------------------------------------------------------------------


def _to_python_identifier(name: str) -> str:
    """Sanitize a string into a valid Python identifier."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if safe and safe[0].isdigit():
        safe = f"_{safe}"
    return safe or "_unnamed"


def _tool_function_source(tool: mcp.types.Tool) -> str:
    """Generate the source for a single ``@call_tool_app.command`` function."""
    schema = tool.inputSchema
    properties: dict[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Build parameter lines
    param_lines: list[str] = []
    call_args: list[str] = []

    for prop_name, prop_schema in properties.items():
        py_type = _schema_type_to_python(prop_schema)
        help_text = prop_schema.get("description", "")
        is_required = prop_name in required
        safe_name = _to_python_identifier(prop_name)

        # Escape quotes in help text
        help_escaped = help_text.replace("\\", "\\\\").replace('"', '\\"')

        if is_required:
            annotation = (
                f'Annotated[{py_type}, cyclopts.Parameter(help="{help_escaped}")]'
            )
            param_lines.append(f"    {safe_name}: {annotation},")
        else:
            default = prop_schema.get("default")
            if default is not None:
                annotation = (
                    f'Annotated[{py_type}, cyclopts.Parameter(help="{help_escaped}")]'
                )
                param_lines.append(f"    {safe_name}: {annotation} = {default!r},")
            else:
                annotation = f'Annotated[{py_type} | None, cyclopts.Parameter(help="{help_escaped}")]'
                param_lines.append(f"    {safe_name}: {annotation} = None,")

        call_args.append(f"{prop_name!r}: {safe_name}")

    # Function name: sanitize to valid Python identifier
    fn_name = _to_python_identifier(tool.name)

    # Docstring
    description = (tool.description or "").replace('"""', '\\"\\"\\"')

    lines = []
    lines.append("")
    # Always pass name= to preserve the original tool name (cyclopts
    # would otherwise convert underscores to hyphens).
    lines.append(f"@call_tool_app.command(name={tool.name!r})")
    lines.append(f"async def {fn_name}(")

    if param_lines:
        lines.append("    *,")
        lines.extend(param_lines)

    lines.append(") -> None:")
    lines.append(f'    """{description}"""')
    dict_items = ", ".join(call_args)
    lines.append(f"    await _call_tool({tool.name!r}, {{{dict_items}}})")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full script generation
# ---------------------------------------------------------------------------


def generate_cli_script(
    server_name: str,
    server_spec: str,
    transport_code: str,
    extra_imports: set[str],
    tools: list[mcp.types.Tool],
) -> str:
    """Generate the full CLI script source code."""

    # Determine app name from server_name
    app_name = server_name.replace(" ", "-").lower()

    # --- Header ---
    lines: list[str] = []
    lines.append("#!/usr/bin/env python3")
    lines.append(f'"""CLI for {server_name} MCP server.')
    lines.append("")
    lines.append(f"Generated by: fastmcp generate-cli {server_spec}")
    lines.append('"""')
    lines.append("")

    # --- Imports ---
    lines.append("import json")
    lines.append("import sys")
    lines.append("from typing import Annotated")
    lines.append("")
    lines.append("import cyclopts")
    lines.append("import mcp.types")
    lines.append("from rich.console import Console")
    lines.append("")
    lines.append("from fastmcp import Client")
    for imp in sorted(extra_imports):
        lines.append(imp)
    lines.append("")

    # --- Transport config ---
    lines.append("# Modify this to change how the CLI connects to the MCP server.")
    lines.append(f"CLIENT_SPEC = {transport_code}")
    lines.append("")

    # --- App setup ---
    server_name_escaped = server_name.replace("\\", "\\\\").replace('"', '\\"')
    lines.append(
        f'app = cyclopts.App(name="{app_name}", help="CLI for {server_name_escaped} MCP server")'
    )
    lines.append(
        'call_tool_app = cyclopts.App(name="call-tool", help="Call a tool on the server")'
    )
    lines.append("app.command(call_tool_app)")
    lines.append("")
    lines.append("console = Console()")
    lines.append("")
    lines.append("")

    # --- Shared helpers ---
    lines.append(
        textwrap.dedent("""\
        # ---------------------------------------------------------------------------
        # Helpers
        # ---------------------------------------------------------------------------


        def _print_tool_result(result):
            if result.is_error:
                for block in result.content:
                    if isinstance(block, mcp.types.TextContent):
                        console.print(f"[bold red]Error:[/bold red] {block.text}")
                    else:
                        console.print(f"[bold red]Error:[/bold red] {block}")
                sys.exit(1)

            if result.structured_content is not None:
                console.print_json(json.dumps(result.structured_content))
                return

            for block in result.content:
                if isinstance(block, mcp.types.TextContent):
                    console.print(block.text)
                elif isinstance(block, mcp.types.ImageContent):
                    size = len(block.data) * 3 // 4
                    console.print(f"[dim][Image: {block.mimeType}, ~{size} bytes][/dim]")
                elif isinstance(block, mcp.types.AudioContent):
                    size = len(block.data) * 3 // 4
                    console.print(f"[dim][Audio: {block.mimeType}, ~{size} bytes][/dim]")


        async def _call_tool(tool_name: str, arguments: dict) -> None:
            filtered = {k: v for k, v in arguments.items() if v is not None}
            async with Client(CLIENT_SPEC) as client:
                result = await client.call_tool(tool_name, filtered, raise_on_error=False)
                _print_tool_result(result)
                if result.is_error:
                    sys.exit(1)""")
    )
    lines.append("")
    lines.append("")

    # --- Generic commands ---
    lines.append(
        textwrap.dedent("""\
        # ---------------------------------------------------------------------------
        # List / read commands
        # ---------------------------------------------------------------------------


        @app.command
        async def list_tools() -> None:
            \"\"\"List available tools.\"\"\"
            async with Client(CLIENT_SPEC) as client:
                tools = await client.list_tools()
                if not tools:
                    console.print("[dim]No tools found.[/dim]")
                    return
                for tool in tools:
                    sig_parts = []
                    props = tool.inputSchema.get("properties", {})
                    required = set(tool.inputSchema.get("required", []))
                    for pname, pschema in props.items():
                        ptype = pschema.get("type", "string")
                        if pname in required:
                            sig_parts.append(f"{pname}: {ptype}")
                        else:
                            sig_parts.append(f"{pname}: {ptype} = ...")
                    sig = f"{tool.name}({', '.join(sig_parts)})"
                    console.print(f"  [cyan]{sig}[/cyan]")
                    if tool.description:
                        console.print(f"    {tool.description}")
                    console.print()


        @app.command
        async def list_resources() -> None:
            \"\"\"List available resources.\"\"\"
            async with Client(CLIENT_SPEC) as client:
                resources = await client.list_resources()
                if not resources:
                    console.print("[dim]No resources found.[/dim]")
                    return
                for r in resources:
                    console.print(f"  [cyan]{r.uri}[/cyan]")
                    desc_parts = [r.name or "", r.description or ""]
                    desc = " — ".join(p for p in desc_parts if p)
                    if desc:
                        console.print(f"    {desc}")
                console.print()


        @app.command
        async def read_resource(uri: Annotated[str, cyclopts.Parameter(help="Resource URI")]) -> None:
            \"\"\"Read a resource by URI.\"\"\"
            async with Client(CLIENT_SPEC) as client:
                contents = await client.read_resource(uri)
                for block in contents:
                    if isinstance(block, mcp.types.TextResourceContents):
                        console.print(block.text)
                    elif isinstance(block, mcp.types.BlobResourceContents):
                        size = len(block.blob) * 3 // 4
                        console.print(f"[dim][Blob: {block.mimeType}, ~{size} bytes][/dim]")


        @app.command
        async def list_prompts() -> None:
            \"\"\"List available prompts.\"\"\"
            async with Client(CLIENT_SPEC) as client:
                prompts = await client.list_prompts()
                if not prompts:
                    console.print("[dim]No prompts found.[/dim]")
                    return
                for p in prompts:
                    args_str = ""
                    if p.arguments:
                        parts = [a.name for a in p.arguments]
                        args_str = f"({', '.join(parts)})"
                    console.print(f"  [cyan]{p.name}{args_str}[/cyan]")
                    if p.description:
                        console.print(f"    {p.description}")
                console.print()


        @app.command
        async def get_prompt(
            name: Annotated[str, cyclopts.Parameter(help="Prompt name")],
            *arguments: str,
        ) -> None:
            \"\"\"Get a prompt by name. Pass arguments as key=value pairs.\"\"\"
            parsed: dict[str, str] = {}
            for arg in arguments:
                if "=" not in arg:
                    console.print(f"[bold red]Error:[/bold red] Invalid argument {arg!r} — expected key=value")
                    sys.exit(1)
                key, value = arg.split("=", 1)
                parsed[key] = value

            async with Client(CLIENT_SPEC) as client:
                result = await client.get_prompt(name, parsed or None)
                for msg in result.messages:
                    console.print(f"[bold]{msg.role}:[/bold]")
                    if isinstance(msg.content, mcp.types.TextContent):
                        console.print(f"  {msg.content.text}")
                    elif isinstance(msg.content, mcp.types.ImageContent):
                        size = len(msg.content.data) * 3 // 4
                        console.print(f"  [dim][Image: {msg.content.mimeType}, ~{size} bytes][/dim]")
                    else:
                        console.print(f"  {msg.content}")
                    console.print()""")
    )
    lines.append("")
    lines.append("")

    # --- Generated tool commands ---
    if tools:
        lines.append(
            "# ---------------------------------------------------------------------------"
        )
        lines.append("# Tool commands (generated from server schema)")
        lines.append(
            "# ---------------------------------------------------------------------------"
        )

        for tool in tools:
            lines.append(_tool_function_source(tool))

    # --- Entry point ---
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    app()")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


async def generate_cli_command(
    server_spec: Annotated[
        str,
        cyclopts.Parameter(
            help="Server URL, Python file, MCPConfig JSON, discovered name, or .js file",
        ),
    ],
    output: Annotated[
        str,
        cyclopts.Parameter(
            help="Output file path (default: cli.py)",
        ),
    ] = "cli.py",
    *,
    force: Annotated[
        bool,
        cyclopts.Parameter(
            name=["-f", "--force"],
            help="Overwrite output file if it exists",
        ),
    ] = False,
    timeout: Annotated[
        float | None,
        cyclopts.Parameter("--timeout", help="Connection timeout in seconds"),
    ] = None,
    auth: Annotated[
        str | None,
        cyclopts.Parameter(
            "--auth",
            help="Auth method: 'oauth', a bearer token string, or 'none' to disable",
        ),
    ] = None,
) -> None:
    """Generate a standalone CLI script from an MCP server.

    Connects to the server, reads its tools/resources/prompts, and writes
    a Python script that can invoke them directly.

    Examples:
        fastmcp generate-cli weather
        fastmcp generate-cli weather my_cli.py
        fastmcp generate-cli http://localhost:8000/mcp
        fastmcp generate-cli server.py output.py -f
    """
    output_path = Path(output)
    if output_path.exists() and not force:
        console.print(
            f"[bold red]Error:[/bold red] [cyan]{output_path}[/cyan] already exists. "
            f"Use [cyan]-f[/cyan] to overwrite."
        )
        sys.exit(1)

    # Resolve the server spec to a transport
    resolved = resolve_server_spec(server_spec)
    transport_code, extra_imports = serialize_transport(resolved)

    # Derive a human-friendly server name from the spec
    server_name = _derive_server_name(server_spec)

    # Connect and discover capabilities
    client = _build_client(resolved, timeout=timeout, auth=auth)

    try:
        async with client:
            tools = await client.list_tools()
            console.print(
                f"[dim]Discovered {len(tools)} tool(s) from {server_spec}[/dim]"
            )

    except (RuntimeError, TimeoutError, McpError, OSError) as exc:
        console.print(f"[bold red]Error:[/bold red] Could not connect: {exc}")
        sys.exit(1)

    # Generate and write the script
    script = generate_cli_script(
        server_name=server_name,
        server_spec=server_spec,
        transport_code=transport_code,
        extra_imports=extra_imports,
        tools=tools,
    )

    output_path.write_text(script)
    output_path.chmod(output_path.stat().st_mode | 0o111)  # make executable

    console.print(
        f"[green]✓[/green] Wrote [cyan]{output_path}[/cyan] "
        f"with {len(tools)} tool command(s)"
    )
    console.print(f"[dim]Run: python {output_path} --help[/dim]")


def _derive_server_name(server_spec: str) -> str:
    """Derive a human-friendly name from a server spec."""
    # URL — use hostname
    if server_spec.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        parsed = urlparse(server_spec)
        return parsed.hostname or "server"

    # File path — use stem
    if server_spec.endswith((".py", ".js", ".json")):
        return Path(server_spec).stem

    # Bare name or qualified name
    if ":" in server_spec:
        name = server_spec.split(":", 1)[1]
        return name or server_spec.split(":", 1)[0]

    return server_spec
