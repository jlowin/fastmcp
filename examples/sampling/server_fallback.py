# /// script
# dependencies = ["anthropic", "fastmcp", "rich"]
# ///
"""
Server-Side Sampling Fallback Example

When the CLIENT has no sampling handler, the SERVER's handler is used instead.

MCP Flow with Fallback:
1. Client calls server tool (client has NO sampling handler)
2. Server tool calls ctx.sample()
3. Client can't handle sampling → server's fallback handler is used
4. Server's handler calls the LLM directly
5. Response returns to server, then to client

Run:
    python examples/sampling/server_fallback.py
"""

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from fastmcp import Client, Context, FastMCP
from fastmcp.server.sampling.anthropic import AnthropicSamplingHandler

console = Console()


# ============================================================================
# SERVER - Note: sampling_handler is on the SERVER, not the client
# ============================================================================


class LoggingAnthropicHandler(AnthropicSamplingHandler):
    async def __call__(self, messages, params, context):
        console.print(
            "      [bold blue]⚡ FALLBACK[/] Server's handler calling Claude...",
            highlight=False,
        )
        result = await super().__call__(messages, params, context)
        console.print(
            "      [bold blue]⚡ FALLBACK[/] Response received", highlight=False
        )
        return result


mcp = FastMCP(
    "Server with Fallback",
    sampling_handler=LoggingAnthropicHandler(default_model="claude-sonnet-4-20250514"),
)


@mcp.tool
async def get_fun_fact(topic: str, ctx: Context) -> str:
    """Get a fun fact about a topic."""
    console.print("   [bold yellow]📦 SERVER[/] Tool 'get_fun_fact' called")
    console.print(
        "   [bold yellow]📦 SERVER[/] Requesting sampling (client has no handler!)"
    )

    result = await ctx.sample(
        messages=f"Tell me one fun fact about: {topic}",
        system_prompt="Share a fascinating fact in 1-2 sentences.",
    )

    console.print("   [bold yellow]📦 SERVER[/] Got response via fallback handler")
    return result.text  # type: ignore[return-value]


@mcp.tool
async def translate(text: str, language: str, ctx: Context) -> str:
    """Translate text to another language."""
    console.print("   [bold yellow]📦 SERVER[/] Tool 'translate' called")
    console.print(
        "   [bold yellow]📦 SERVER[/] Requesting sampling (client has no handler!)"
    )

    result = await ctx.sample(
        messages=f"Translate to {language}: {text}",
        system_prompt="Provide only the translation.",
    )

    console.print("   [bold yellow]📦 SERVER[/] Got response via fallback handler")
    return result.text  # type: ignore[return-value]


# ============================================================================
# CLIENT - Note: NO sampling_handler provided!
# ============================================================================


async def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold]Server Fallback Example[/]\n\n"
            "The [green]CLIENT[/] has [bold red]no sampling handler[/].\n"
            "The [yellow]SERVER's[/] fallback handler is used instead.",
            border_style="bright_black",
        )
    )
    console.print()

    # IMPORTANT: No sampling_handler!
    async with Client(mcp) as client:
        console.rule(style="dim")
        console.print(
            "[bold green]🖥️  CLIENT[/] Calling 'get_fun_fact' [dim](no sampling handler!)[/]"
        )
        console.print()

        result = await client.call_tool("get_fun_fact", {"topic": "octopuses"})

        console.print()
        console.print("[bold green]🖥️  CLIENT[/] Result:")
        console.print(Panel(result.data, border_style="green"))
        console.print()

        console.rule(style="dim")
        console.print(
            "[bold green]🖥️  CLIENT[/] Calling 'translate' [dim](no sampling handler!)[/]"
        )
        console.print()

        result = await client.call_tool(
            "translate", {"text": "Hello, how are you?", "language": "Spanish"}
        )

        console.print()
        console.print("[bold green]🖥️  CLIENT[/] Result:")
        console.print(Panel(result.data, border_style="green"))
        console.print()

    # Summary
    summary = Text()
    summary.append("Key concept: ", style="bold")
    summary.append(
        "When the client lacks sampling support, the server's\n"
        "fallback handler steps in. This lets servers guarantee\n"
        "sampling works regardless of client capabilities."
    )

    console.print(Panel(summary, border_style="bright_black"))
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
