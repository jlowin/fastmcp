# /// script
# dependencies = ["anthropic", "fastmcp", "rich"]
# ///
"""
Text Sampling Example

The simplest form of sampling: send text to an LLM and get text back.

MCP Sampling Flow:
1. Client calls a tool on the server
2. Server tool needs LLM help, makes a sampling request
3. The sampling handler (on client) calls the LLM
4. Response flows back through the chain

Run:
    python examples/sampling/text.py
"""

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from fastmcp import Client, Context, FastMCP
from fastmcp.server.sampling.anthropic import AnthropicSamplingHandler

console = Console()


# ============================================================================
# SAMPLING HANDLER WITH LOGGING
# Wraps AnthropicSamplingHandler to show when LLM calls happen
# ============================================================================


class LoggingAnthropicHandler(AnthropicSamplingHandler):
    """Sampling handler that logs when it calls the LLM."""

    async def __call__(self, messages, params, context):
        console.print(
            "      [bold blue]⚡ SAMPLING[/] Calling Claude API...", highlight=False
        )
        result = await super().__call__(messages, params, context)
        console.print(
            "      [bold blue]⚡ SAMPLING[/] Response received", highlight=False
        )
        return result


# ============================================================================
# SERVER
# ============================================================================

mcp = FastMCP("Creative Writer")


@mcp.tool
async def write_haiku(topic: str, ctx: Context) -> str:
    """Write a haiku about the given topic."""
    console.print(
        f"   [bold yellow]📦 SERVER[/] Tool 'write_haiku' called with topic={topic!r}"
    )
    console.print("   [bold yellow]📦 SERVER[/] Requesting LLM completion...")

    result = await ctx.sample(
        messages=f"Write a haiku about: {topic}",
        system_prompt="You are a poet. Write only the haiku, nothing else.",
    )

    console.print("   [bold yellow]📦 SERVER[/] Returning result to client")
    return result.text  # type: ignore[return-value]


@mcp.tool
async def explain_simply(concept: str, ctx: Context) -> str:
    """Explain a concept in simple terms."""
    console.print(
        f"   [bold yellow]📦 SERVER[/] Tool 'explain_simply' called with concept={concept!r}"
    )
    console.print("   [bold yellow]📦 SERVER[/] Requesting LLM completion...")

    result = await ctx.sample(
        messages=f"Explain this concept: {concept}",
        system_prompt="Explain in 1-2 simple sentences a child could understand.",
    )

    console.print("   [bold yellow]📦 SERVER[/] Returning result to client")
    return result.text  # type: ignore[return-value]


# ============================================================================
# CLIENT
# ============================================================================


async def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold]Text Sampling Example[/]\n\n"
            "Watch the flow: [green]CLIENT[/] → [yellow]SERVER[/] → [blue]SAMPLING[/] → [yellow]SERVER[/] → [green]CLIENT[/]",
            border_style="bright_black",
        )
    )
    console.print()

    handler = LoggingAnthropicHandler(default_model="claude-sonnet-4-20250514")

    async with Client(mcp, sampling_handler=handler) as client:
        # Example 1
        console.rule("[bold green]Example 1: Write a Haiku", style="green")
        console.print("[bold green]🖥️  CLIENT[/] Calling tool 'write_haiku'")
        console.print()

        result = await client.call_tool("write_haiku", {"topic": "async programming"})

        console.print()
        console.print("[bold green]🖥️  CLIENT[/] Got result:")
        console.print(Panel(result.data, border_style="green", padding=(0, 2)))
        console.print()

        # Example 2
        console.rule("[bold green]Example 2: Simple Explanation", style="green")
        console.print("[bold green]🖥️  CLIENT[/] Calling tool 'explain_simply'")
        console.print()

        result = await client.call_tool("explain_simply", {"concept": "recursion"})

        console.print()
        console.print("[bold green]🖥️  CLIENT[/] Got result:")
        console.print(Panel(result.data, border_style="green", padding=(0, 2)))
        console.print()

    # Summary
    summary = Text()
    summary.append("Flow: ", style="bold")
    summary.append("CLIENT", style="green")
    summary.append(" calls tool → ")
    summary.append("SERVER", style="yellow")
    summary.append(" needs LLM → ")
    summary.append("SAMPLING", style="blue")
    summary.append(" calls Claude → response flows back")

    console.print(
        Panel(summary, title="[bold]How it works[/]", border_style="bright_black")
    )
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
