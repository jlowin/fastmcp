"""Tests for max_sampling_rounds parameter."""

import pytest
from mcp.types import CreateMessageResultWithTools, TextContent, ToolUseContent

from fastmcp import Client, Context, FastMCP
from fastmcp.client.sampling import RequestContext, SamplingMessage, SamplingParams
from fastmcp.exceptions import ToolError


async def test_max_sampling_rounds_default():
    """Test that default max_sampling_rounds is 100."""
    call_count = 0

    def loop_tool() -> str:
        """A tool that the LLM will keep calling."""
        nonlocal call_count
        call_count += 1
        return "keep going"

    # Handler that always returns tool use to create an infinite loop
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> CreateMessageResultWithTools:
        # Always request tool use to create infinite loop
        return CreateMessageResultWithTools(
            role="assistant",
            content=[
                ToolUseContent(
                    type="tool_use",
                    id="call_1",
                    name="loop_tool",
                    input={},
                )
            ],
            model="test-model",
            stopReason="toolUse",
        )

    mcp = FastMCP(sampling_handler=sampling_handler)

    @mcp.tool
    async def infinite_tool(context: Context) -> str:
        """Tool that never stops calling itself."""
        result = await context.sample(
            "Keep calling loop_tool",
            tools=[loop_tool],
        )
        return result.text or ""

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="Sampling exceeded maximum iterations \\(100\\)"):
            await client.call_tool("infinite_tool", {})

        # Verify it actually made 100 iterations
        assert call_count == 100


async def test_max_sampling_rounds_custom():
    """Test that custom max_sampling_rounds works."""
    call_count = 0

    def loop_tool() -> str:
        """A tool that the LLM will keep calling."""
        nonlocal call_count
        call_count += 1
        return "keep going"

    # Handler that always returns tool use
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> CreateMessageResultWithTools:
        return CreateMessageResultWithTools(
            role="assistant",
            content=[
                ToolUseContent(
                    type="tool_use",
                    id="call_1",
                    name="loop_tool",
                    input={},
                )
            ],
            model="test-model",
            stopReason="toolUse",
        )

    mcp = FastMCP(sampling_handler=sampling_handler)

    @mcp.tool
    async def limited_tool(context: Context) -> str:
        """Tool with custom max rounds."""
        result = await context.sample(
            "Keep calling loop_tool",
            tools=[loop_tool],
            max_sampling_rounds=5,
        )
        return result.text or ""

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="Sampling exceeded maximum iterations \\(5\\)"):
            await client.call_tool("limited_tool", {})

        # Verify it only made 5 iterations
        assert call_count == 5


async def test_max_sampling_rounds_completes_normally():
    """Test that sampling completes normally when rounds don't exceed limit."""
    call_count = 0

    def helper_tool() -> str:
        """A helper tool."""
        return "done"

    # Handler that returns tool use once, then text response
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> CreateMessageResultWithTools:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First call: request tool use
            return CreateMessageResultWithTools(
                role="assistant",
                content=[
                    ToolUseContent(
                        type="tool_use",
                        id="call_1",
                        name="helper_tool",
                        input={},
                    )
                ],
                model="test-model",
                stopReason="toolUse",
            )
        else:
            # Second call: return text response
            return CreateMessageResultWithTools(
                role="assistant",
                content=[TextContent(type="text", text="All done!")],
                model="test-model",
                stopReason="endTurn",
            )

    mcp = FastMCP(sampling_handler=sampling_handler)

    @mcp.tool
    async def normal_tool(context: Context) -> str:
        """Tool that completes normally."""
        result = await context.sample(
            "Use helper_tool once",
            tools=[helper_tool],
            max_sampling_rounds=10,
        )
        return result.text or ""

    async with Client(mcp) as client:
        result = await client.call_tool("normal_tool", {})
        assert result.data == "All done!"
        assert call_count == 2  # Should only take 2 iterations
