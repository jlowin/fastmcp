# /// script
# dependencies = ["anthropic", "fastmcp", "rich"]
# ///
"""
Structured Output Example

Use `result_type` to get validated Pydantic models from an LLM.

MCP Flow:
1. Client calls server tool
2. Server makes sampling request with result_type=YourModel
3. LLM response is parsed and validated against the Pydantic schema
4. Server returns structured data to client

Run:
    python examples/sampling/structured_output.py
"""

import asyncio
from enum import Enum

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from fastmcp import Client, Context, FastMCP
from fastmcp.server.sampling.anthropic import AnthropicSamplingHandler

console = Console()


# ============================================================================
# PYDANTIC MODELS - Define the schema for LLM responses
# ============================================================================


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class SentimentAnalysis(BaseModel):
    sentiment: Sentiment = Field(description="Overall sentiment")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0.0-1.0")
    reasoning: str = Field(description="Brief explanation")
    key_phrases: list[str] = Field(description="Influential phrases")


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

mcp = FastMCP("Sentiment Analyzer")


@mcp.tool
async def analyze_sentiment(text: str, ctx: Context) -> dict:
    """Analyze sentiment and return structured results."""
    console.print("   [bold yellow]📦 SERVER[/] Tool 'analyze_sentiment' called")
    console.print(
        "   [bold yellow]📦 SERVER[/] Sampling with result_type=SentimentAnalysis"
    )

    result = await ctx.sample(
        messages=f"Analyze the sentiment of this text:\n\n{text}",
        system_prompt="You are a sentiment analysis expert.",
        result_type=SentimentAnalysis,
    )

    console.print(
        f"   [bold yellow]📦 SERVER[/] Got validated {type(result.result).__name__}"
    )
    return result.result.model_dump()  # type: ignore[union-attr]


# ============================================================================
# CLIENT
# ============================================================================


async def main():
    console.print()
    console.print(
        Panel.fit(
            "[bold]Structured Output Example[/]\n\n"
            "The [cyan]result_type[/] parameter ensures LLM responses\n"
            "match your Pydantic schema.",
            border_style="bright_black",
        )
    )
    console.print()

    handler = LoggingAnthropicHandler(default_model="claude-sonnet-4-20250514")

    test_texts = [
        ("I love this! Best purchase ever!", "😊"),
        ("Terrible. Would not recommend.", "😞"),
        ("It's okay. Nothing special.", "😐"),
    ]

    async with Client(mcp, sampling_handler=handler) as client:
        for text, _ in test_texts:
            console.rule(style="dim")
            console.print(f"[bold green]🖥️  CLIENT[/] Analyzing: [italic]{text}[/]")
            console.print()

            result = await client.call_tool("analyze_sentiment", {"text": text})
            data = result.data

            # Display result in a nice table
            console.print()
            console.print("[bold green]🖥️  CLIENT[/] Received structured result:")

            emoji = {"positive": "😊", "negative": "😞", "neutral": "😐", "mixed": "🤔"}

            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column(style="bold")
            table.add_column()
            table.add_row(
                "Sentiment", f"{emoji.get(data['sentiment'], '❓')} {data['sentiment']}"
            )
            table.add_row(
                "Confidence",
                f"[green]{'█' * int(data['confidence'] * 10)}[/][dim]{'░' * (10 - int(data['confidence'] * 10))}[/] {data['confidence']:.0%}",
            )
            table.add_row("Reasoning", data["reasoning"])
            table.add_row("Key phrases", ", ".join(data["key_phrases"]))

            console.print(Panel(table, border_style="green"))
            console.print()

    console.print(
        Panel(
            "[bold]Key concept:[/] The result_type parameter enforces a Pydantic schema.\n"
            "Invalid LLM responses are automatically rejected and retried.",
            border_style="bright_black",
        )
    )
    console.print()


if __name__ == "__main__":
    asyncio.run(main())
