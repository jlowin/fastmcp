"""Types for bulk tool caller."""

from typing import Any

from mcp.types import CallToolResult
from pydantic import BaseModel, Field


class CallToolRequest(BaseModel):
    """A class to represent a request to call a tool with specific arguments."""

    tool: str = Field(description="The name of the tool to call.")
    arguments: dict[str, Any] = Field(
        description="A dictionary containing the arguments for the tool call."
    )


class CallToolRequestResult(CallToolResult):
    """A class to represent the result of a bulk tool call.

    It extends CallToolResult to include information about the requested tool call.
    """

    tool: str = Field(description="The name of the tool that was called.")
    arguments: dict[str, Any] = Field(
        description="The arguments used for the tool call."
    )

    @classmethod
    def from_call_tool_result(
        cls, result: CallToolResult, tool: str, arguments: dict[str, Any]
    ) -> "CallToolRequestResult":
        """Create a CallToolRequestResult from a CallToolResult."""
        return cls(
            tool=tool,
            arguments=arguments,
            isError=result.isError,
            content=result.content,
        )
