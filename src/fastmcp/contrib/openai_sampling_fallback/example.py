import asyncio
import os

from mcp.types import ContentBlock
from openai import OpenAI

from fastmcp import FastMCP
from fastmcp.contrib.openai_sampling_fallback import OpenAISampling
from fastmcp.server.context import Context


async def async_main():
    server = FastMCP(
        name="OpenAI Sampling Fallback Example",
        sampling_fallback=OpenAISampling(
            default_model=os.getenv("MODEL") or "gpt-4o-mini",  # pyright: ignore[reportArgumentType]
            client=OpenAI(
                api_key=os.getenv("API_KEY"),
                base_url=os.getenv("BASE_URL"),
            ),
        ),
    )

    @server.tool
    async def test_sample_fallback(ctx: Context) -> ContentBlock:
        return await ctx.sample(
            messages=["hello world!"],
        )

    await server.run_sse_async()


if __name__ == "__main__":
    asyncio.run(async_main())
