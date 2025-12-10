# /// script
# dependencies = ["anthropic", "fastmcp", "rich"]
# ///
"""
Tool Use Example

Give the LLM tools to use during sampling.

MCP Flow with Tools:
1. Client calls server tool
2. Server makes sampling request with tools=[...]
3. LLM decides to call a tool → tool executes → result fed back to LLM
4. Loop continues until LLM gives final answer (or max_iterations)
5. Server returns final response to client

Run:
    python examples/sampling/tool_use.py
"""

import asyncio
import random
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from fastmcp import Client, Context, FastMCP
from fastmcp.server.sampling.anthropic import AnthropicSamplingHandler

console = Console()


# ============================================================================
# TOOLS - Functions the LLM can call during sampling
# ============================================================================


def calculate(expression: str) -> str:
    """Evaluate a math expression. Use Python syntax (e.g., 2**10 for power)."""
    console.print(
        f"         [bold magenta]🔧 TOOL[/] calculate({expression!r})", highlight=False
    )
    try:
        allowed = {"abs": abs, "round": round, "min": min, "max": max}
        result = eval(expression, {"__builtins__": {}}, allowed)
        console.print(f"         [bold magenta]🔧 TOOL[/] → {result}", highlight=False)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def get_current_time() -> str:
    """Get the current date and time."""
    console.print(
        "         [bold magenta]🔧 TOOL[/] get_current_time()", highlight=False
    )
    result = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    console.print(f"         [bold magenta]🔧 TOOL[/] → {result}", highlight=False)
    return result


def roll_dice(sides: int = 6, count: int = 1) -> str:
    """Roll dice and return results."""
    console.print(
        f"         [bold magenta]🔧 TOOL[/] roll_dice(sides={sides}, count={count})",
        highlight=False,
    )
    rolls = [random.randint(1, sides) for _ in range(count)]
    result = f"Rolled {count}d{sides}: {rolls} (total: {sum(rolls)})"
    console.print(f"         [bold magenta]🔧 TOOL[/] → {result}", highlight=False)
    return result


# ============================================================================
# SAMPLING HANDLER WITH LOGGING
# ============================================================================


class LoggingAnthropicHandler(AnthropicSamplingHandler):
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

mcp = FastMCP("Assistant with Tools")


@mcp.tool
async def ask(question: str, ctx: Context) -> str:
    """Ask a question. The LLM can use tools to help answer."""
    console.print("   [bold yellow]📦 SERVER[/] Tool 'ask' called")
    console.print(
        "   [bold yellow]📦 SERVER[/] Sampling with tools=[calculate, get_current_time, roll_dice]"
    )
    console.print()

    result = await ctx.sample(
        messages=question,
        system_prompt="You have tools available. Use them when helpful. Be concise.",
        tools=[calculate, get_current_time, roll_dice],
        max_iterations=5,
    )

    console.print()
    console.print("   [bold yellow]📦 SERVER[/] Tool loop complete, returning answer")
    return result.text  # type: ignore[return-value]


# ============================================================================
# CLIENT
# ============================================================================


async def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold]Tool Use Example[/]\n\n"
            "Watch the LLM use [magenta]TOOLS[/] during sampling.\n"
            "The tool loop runs until the LLM has a final answer.",
            border_style="bright_black",
        )
    )
    console.print()

    handler = LoggingAnthropicHandler(default_model="claude-sonnet-4-5-20250929")

    questions = [
        "What's 15% tip on a $47.50 bill?",
        "What time is it right now?",
        "Roll 2 dice and tell me if I got doubles.",
    ]

    async with Client(mcp, sampling_handler=handler) as client:
        for question in questions:
            console.rule(style="dim")
            console.print(f"[bold green]🖥️  CLIENT[/] Question: [italic]{question}[/]")
            console.print()

            result = await client.call_tool("ask", {"question": question})

            console.print()
            console.print("[bold green]🖥️  CLIENT[/] Answer:")
            console.print(Panel(result.data, border_style="green"))
            console.print()

    console.print(
        Panel(
            "[bold]Key concept:[/] The [cyan]tools[/] parameter lets the LLM call functions.\n"
            "FastMCP handles the tool execution loop automatically.\n"
            "[cyan]max_iterations[/] prevents infinite loops.",
            border_style="bright_black",
        )
    )
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
