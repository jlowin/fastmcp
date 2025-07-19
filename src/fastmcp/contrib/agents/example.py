import asyncio
import os

from openai import OpenAI

from fastmcp import FastMCP
from fastmcp.contrib.agents.base import AgentTool
from fastmcp.contrib.agents.curator import AskCuratorAgent, TellCuratorAgent
from fastmcp.contrib.openai_completions import OpenAILLMCompletions
from fastmcp.server.context import Context


async def async_main():
    server = FastMCP(
        name="OpenAI Completions Example",
        llm_completions=OpenAILLMCompletions(
            default_model=os.getenv("MODEL") or "gpt-4o-mini",  # pyright: ignore[reportArgumentType]
            client=OpenAI(
                api_key=os.getenv("API_KEY"),
                base_url=os.getenv("BASE_URL"),
            ),
        ),
        tools=[
            AgentTool.from_agent(AskCuratorAgent(name="ask_curator")),
            AgentTool.from_agent(TellCuratorAgent(name="tell_curator")),
        ],
    )

    @server.tool
    async def get_capital_of_country_tool(ctx: Context, country: str) -> str:
        return "Paris"

    await server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(async_main())
