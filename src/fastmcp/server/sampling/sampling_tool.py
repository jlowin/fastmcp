"""SamplingTool for use during LLM sampling requests."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, overload

from mcp.types import Tool as SDKTool
from pydantic import BaseModel, ConfigDict

from fastmcp.tools.tool import ParsedFunction

if TYPE_CHECKING:
    from fastmcp.tools.tool import Tool


class SamplingTool(BaseModel):
    """A tool that can be used during LLM sampling.

    SamplingTools bundle a tool's schema (name, description, parameters) with
    an executor function, enabling servers to execute agentic workflows where
    the LLM can request tool calls during sampling.

    Create a SamplingTool using the @sampling_tool decorator or class methods:

        @sampling_tool
        def search(query: str) -> str:
            '''Search the web.'''
            return web_search(query)

        # Or from an existing FastMCP Tool
        sampling_tool = SamplingTool.from_mcp_tool(existing_tool)

        # Then use in sampling
        result = await context.sample(
            messages="Find info about Python",
            tools=[search],
        )
    """

    name: str
    description: str | None = None
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def run(self, arguments: dict[str, Any] | None = None) -> Any:
        """Execute the tool with the given arguments.

        Args:
            arguments: Dictionary of arguments to pass to the tool function.

        Returns:
            The result of executing the tool function.
        """
        if arguments is None:
            arguments = {}

        result = self.fn(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return result

    def _to_sdk_tool(self) -> SDKTool:
        """Convert to an mcp.types.Tool for SDK compatibility.

        This is used internally when passing tools to the MCP SDK's
        create_message() method.
        """
        return SDKTool(
            name=self.name,
            description=self.description,
            inputSchema=self.parameters,
        )

    @classmethod
    def from_mcp_tool(cls, tool: Tool) -> SamplingTool:
        """Create a SamplingTool from a FastMCP Tool.

        Args:
            tool: A FastMCP Tool instance (must have an fn attribute).

        Returns:
            A SamplingTool with the same schema and executor.

        Raises:
            ValueError: If the tool doesn't have an fn attribute.
        """
        if not hasattr(tool, "fn"):
            raise ValueError(
                f"Tool {tool.name!r} does not have an fn attribute. "
                "Only FunctionTools can be converted to SamplingTools."
            )

        return cls(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            fn=tool.fn,
        )

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> SamplingTool:
        """Create a SamplingTool from a function.

        The function's signature is analyzed to generate a JSON schema for
        the tool's parameters. Type hints are used to determine parameter types.

        Args:
            fn: The function to create a tool from.
            name: Optional name override. Defaults to the function's name.
            description: Optional description override. Defaults to the function's docstring.

        Returns:
            A SamplingTool wrapping the function.

        Raises:
            ValueError: If the function is a lambda without a name override.
        """
        parsed = ParsedFunction.from_function(fn, validate=True)

        if name is None and parsed.name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        return cls(
            name=name or parsed.name,
            description=description or parsed.description,
            parameters=parsed.input_schema,
            fn=parsed.fn,
        )


@overload
def sampling_tool(fn: Callable[..., Any]) -> SamplingTool: ...


@overload
def sampling_tool(
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[..., Any]], SamplingTool]: ...


def sampling_tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> SamplingTool | Callable[[Callable[..., Any]], SamplingTool]:
    """Decorator to create a SamplingTool from a function.

    Can be used with or without arguments:

        @sampling_tool
        def search(query: str) -> str:
            '''Search the web.'''
            return web_search(query)

        @sampling_tool(name="web_search", description="Search the internet")
        def search(query: str) -> str:
            return web_search(query)

    Args:
        fn: The function to wrap (when used without parentheses).
        name: Optional name override for the tool.
        description: Optional description override for the tool.

    Returns:
        A SamplingTool if called directly on a function, or a decorator
        if called with arguments.
    """
    if fn is not None:
        return SamplingTool.from_function(fn)

    def decorator(fn: Callable[..., Any]) -> SamplingTool:
        return SamplingTool.from_function(fn, name=name, description=description)

    return decorator
