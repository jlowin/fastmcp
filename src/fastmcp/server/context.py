from __future__ import annotations

import copy
import inspect
import json
import logging
import weakref
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from logging import Logger
from typing import Any, Generic, Literal, cast, get_origin, overload

import anyio
from mcp import LoggingLevel, ServerSession
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from mcp.types import (
    ClientCapabilities,
    CreateMessageResult,
    CreateMessageResultWithTools,
    GetPromptResult,
    IncludeContext,
    ModelHint,
    ModelPreferences,
    Root,
    SamplingCapability,
    SamplingMessage,
    SamplingMessageContentBlock,
    SamplingToolsCapability,
    TextContent,
    ToolChoice,
    ToolResultContent,
    ToolUseContent,
)
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import Prompt as SDKPrompt
from mcp.types import Resource as SDKResource
from mcp.types import Tool as SDKTool
from pydantic.networks import AnyUrl
from starlette.requests import Request
from typing_extensions import TypeVar

from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
    ScalarElicitationType,
    get_elicitation_schema,
)
from fastmcp.server.sampling import SamplingTool
from fastmcp.server.server import FastMCP
from fastmcp.tools.tool import Tool as FastMCPTool
from fastmcp.utilities.json_schema import compress_schema
from fastmcp.utilities.logging import _clamp_logger, get_logger
from fastmcp.utilities.types import get_cached_typeadapter

logger: Logger = get_logger(name=__name__)
to_client_logger: Logger = logger.getChild(suffix="to_client")

# Convert all levels of server -> client messages to debug level
# This clamp can be undone at runtime by calling `_unclamp_logger` or calling
# `_clamp_logger` with a different max level.
_clamp_logger(logger=to_client_logger, max_level="DEBUG")


T = TypeVar("T", default=Any)
ResultT = TypeVar("ResultT", default=str)

_current_context: ContextVar[Context | None] = ContextVar("context", default=None)  # type: ignore[assignment]


@dataclass
class SamplingResult(Generic[ResultT]):
    """Result from ctx.sample() containing the response and history.

    This is a generic class where ResultT defaults to str for text responses.
    When a result_type is specified, ResultT is that type.

    Attributes:
        text: The text representation of the result. For text responses, this is
            the raw text. For structured responses, this is the JSON representation.
            None if the response was a tool use (for manual loop building).
        result: The typed result. When ResultT is str, this equals text. When ResultT
            is a custom type, this is the validated/parsed object.
        history: List of all messages exchanged during sampling, including tool calls
            and results. Useful for continuing conversations or debugging.
    """

    text: str | None
    result: ResultT
    history: list[SamplingMessage]


_flush_lock = anyio.Lock()


@dataclass
class LogData:
    """Data object for passing log arguments to client-side handlers.

    This provides an interface to match the Python standard library logging,
    for compatibility with structured logging.
    """

    msg: str
    extra: Mapping[str, Any] | None = None


_mcp_level_to_python_level = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


@contextmanager
def set_context(context: Context) -> Generator[Context, None, None]:
    token = _current_context.set(context)
    try:
        yield context
    finally:
        _current_context.reset(token)


@dataclass
class Context:
    """Context object providing access to MCP capabilities.

    This provides a cleaner interface to MCP's RequestContext functionality.
    It gets injected into tool and resource functions that request it via type hints.

    To use context in a tool function, add a parameter with the Context type annotation:

    ```python
    @server.tool
    async def my_tool(x: int, ctx: Context) -> str:
        # Log messages to the client
        await ctx.info(f"Processing {x}")
        await ctx.debug("Debug info")
        await ctx.warning("Warning message")
        await ctx.error("Error message")

        # Report progress
        await ctx.report_progress(50, 100, "Processing")

        # Access resources
        data = await ctx.read_resource("resource://data")

        # Get request info
        request_id = ctx.request_id
        client_id = ctx.client_id

        # Manage state across the request
        ctx.set_state("key", "value")
        value = ctx.get_state("key")

        return str(x)
    ```

    State Management:
    Context objects maintain a state dictionary that can be used to store and share
    data across middleware and tool calls within a request. When a new context
    is created (nested contexts), it inherits a copy of its parent's state, ensuring
    that modifications in child contexts don't affect parent contexts.

    The context parameter name can be anything as long as it's annotated with Context.
    The context is optional - tools that don't need it can omit the parameter.

    """

    def __init__(self, fastmcp: FastMCP):
        self._fastmcp: weakref.ref[FastMCP] = weakref.ref(fastmcp)
        self._tokens: list[Token] = []
        self._notification_queue: set[str] = set()  # Dedupe notifications
        self._state: dict[str, Any] = {}

    @property
    def fastmcp(self) -> FastMCP:
        """Get the FastMCP instance."""
        fastmcp = self._fastmcp()
        if fastmcp is None:
            raise RuntimeError("FastMCP instance is no longer available")
        return fastmcp

    async def __aenter__(self) -> Context:
        """Enter the context manager and set this context as the current context."""
        parent_context = _current_context.get(None)
        if parent_context is not None:
            # Inherit state from parent context
            self._state = copy.deepcopy(parent_context._state)

        # Always set this context and save the token
        token = _current_context.set(self)
        self._tokens.append(token)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and reset the most recent token."""
        # Flush any remaining notifications before exiting
        await self._flush_notifications()

        if self._tokens:
            token = self._tokens.pop()
            _current_context.reset(token)

    @property
    def request_context(self) -> RequestContext[ServerSession, Any, Request] | None:
        """Access to the underlying request context.

        Returns None when the MCP session has not been established yet.
        Returns the full RequestContext once the MCP session is available.

        For HTTP request access in middleware, use `get_http_request()` from fastmcp.server.dependencies,
        which works whether or not the MCP session is available.

        Example in middleware:
        ```python
        async def on_request(self, context, call_next):
            ctx = context.fastmcp_context
            if ctx.request_context:
                # MCP session available - can access session_id, request_id, etc.
                session_id = ctx.session_id
            else:
                # MCP session not available yet - use HTTP helpers
                from fastmcp.server.dependencies import get_http_request
                request = get_http_request()
            return await call_next(context)
        ```
        """
        try:
            return request_ctx.get()
        except LookupError:
            return None

    async def report_progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        """Report progress for the current operation.

        Args:
            progress: Current progress value e.g. 24
            total: Optional total value e.g. 100
        """

        progress_token = (
            self.request_context.meta.progressToken
            if self.request_context and self.request_context.meta
            else None
        )

        if progress_token is None:
            return

        await self.session.send_progress_notification(
            progress_token=progress_token,
            progress=progress,
            total=total,
            message=message,
            related_request_id=self.request_id,
        )

    async def list_resources(self) -> list[SDKResource]:
        """List all available resources from the server.

        Returns:
            List of Resource objects available on the server
        """
        return await self.fastmcp._list_resources_mcp()

    async def list_prompts(self) -> list[SDKPrompt]:
        """List all available prompts from the server.

        Returns:
            List of Prompt objects available on the server
        """
        return await self.fastmcp._list_prompts_mcp()

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> GetPromptResult:
        """Get a prompt by name with optional arguments.

        Args:
            name: The name of the prompt to get
            arguments: Optional arguments to pass to the prompt

        Returns:
            The prompt result
        """
        return await self.fastmcp._get_prompt_mcp(name, arguments)

    async def read_resource(self, uri: str | AnyUrl) -> list[ReadResourceContents]:
        """Read a resource by URI.

        Args:
            uri: Resource URI to read

        Returns:
            The resource content as either text or bytes
        """
        return await self.fastmcp._read_resource_mcp(uri)

    async def log(
        self,
        message: str,
        level: LoggingLevel | None = None,
        logger_name: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a log message to the client.

        Messages sent to Clients are also logged to the `fastmcp.server.context.to_client` logger with a level of `DEBUG`.

        Args:
            message: Log message
            level: Optional log level. One of "debug", "info", "notice", "warning", "error", "critical",
                "alert", or "emergency". Default is "info".
            logger_name: Optional logger name
            extra: Optional mapping for additional arguments
        """
        data = LogData(msg=message, extra=extra)

        await _log_to_server_and_client(
            data=data,
            session=self.session,
            level=level or "info",
            logger_name=logger_name,
            related_request_id=self.request_id,
        )

    @property
    def client_id(self) -> str | None:
        """Get the client ID if available."""
        return (
            getattr(self.request_context.meta, "client_id", None)
            if self.request_context and self.request_context.meta
            else None
        )

    @property
    def request_id(self) -> str:
        """Get the unique ID for this request.

        Raises RuntimeError if MCP request context is not available.
        """
        if self.request_context is None:
            raise RuntimeError(
                "request_id is not available because the MCP session has not been established yet. "
                "Check `context.request_context` for None before accessing this attribute."
            )
        return str(self.request_context.request_id)

    @property
    def session_id(self) -> str:
        """Get the MCP session ID for ALL transports.

        Returns the session ID that can be used as a key for session-based
        data storage (e.g., Redis) to share data between tool calls within
        the same client session.

        Returns:
            The session ID for StreamableHTTP transports, or a generated ID
            for other transports.

        Raises:
            RuntimeError if MCP request context is not available.

        Example:
            ```python
            @server.tool
            def store_data(data: dict, ctx: Context) -> str:
                session_id = ctx.session_id
                redis_client.set(f"session:{session_id}:data", json.dumps(data))
                return f"Data stored for session {session_id}"
            ```
        """
        request_ctx = self.request_context
        if request_ctx is None:
            raise RuntimeError(
                "session_id is not available because the MCP session has not been established yet. "
                "Check `context.request_context` for None before accessing this attribute."
            )
        session = request_ctx.session

        # Try to get the session ID from the session attributes
        session_id = getattr(session, "_fastmcp_id", None)
        if session_id is not None:
            return session_id

        # Try to get the session ID from the http request headers
        request = request_ctx.request
        if request:
            session_id = request.headers.get("mcp-session-id")

        # Generate a session ID if it doesn't exist.
        if session_id is None:
            from uuid import uuid4

            session_id = str(uuid4())

        # Save the session id to the session attributes
        session._fastmcp_id = session_id
        return session_id

    @property
    def session(self) -> ServerSession:
        """Access to the underlying session for advanced usage.

        Raises RuntimeError if MCP request context is not available.
        """
        if self.request_context is None:
            raise RuntimeError(
                "session is not available because the MCP session has not been established yet. "
                "Check `context.request_context` for None before accessing this attribute."
            )
        return self.request_context.session

    # Convenience methods for common log levels
    async def debug(
        self,
        message: str,
        logger_name: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a `DEBUG`-level message to the connected MCP Client.

        Messages sent to Clients are also logged to the `fastmcp.server.context.to_client` logger with a level of `DEBUG`."""
        await self.log(
            level="debug",
            message=message,
            logger_name=logger_name,
            extra=extra,
        )

    async def info(
        self,
        message: str,
        logger_name: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a `INFO`-level message to the connected MCP Client.

        Messages sent to Clients are also logged to the `fastmcp.server.context.to_client` logger with a level of `DEBUG`."""
        await self.log(
            level="info",
            message=message,
            logger_name=logger_name,
            extra=extra,
        )

    async def warning(
        self,
        message: str,
        logger_name: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a `WARNING`-level message to the connected MCP Client.

        Messages sent to Clients are also logged to the `fastmcp.server.context.to_client` logger with a level of `DEBUG`."""
        await self.log(
            level="warning",
            message=message,
            logger_name=logger_name,
            extra=extra,
        )

    async def error(
        self,
        message: str,
        logger_name: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a `ERROR`-level message to the connected MCP Client.

        Messages sent to Clients are also logged to the `fastmcp.server.context.to_client` logger with a level of `DEBUG`."""
        await self.log(
            level="error",
            message=message,
            logger_name=logger_name,
            extra=extra,
        )

    async def list_roots(self) -> list[Root]:
        """List the roots available to the server, as indicated by the client."""
        result = await self.session.list_roots()
        return result.roots

    async def send_tool_list_changed(self) -> None:
        """Send a tool list changed notification to the client."""
        await self.session.send_tool_list_changed()

    async def send_resource_list_changed(self) -> None:
        """Send a resource list changed notification to the client."""
        await self.session.send_resource_list_changed()

    async def send_prompt_list_changed(self) -> None:
        """Send a prompt list changed notification to the client."""
        await self.session.send_prompt_list_changed()

    @overload
    async def sample(
        self,
        messages: str | Sequence[str | SamplingMessage],
        *,
        system_prompt: str | None = None,
        include_context: IncludeContext | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_preferences: ModelPreferences | str | list[str] | None = None,
        tools: Sequence[SamplingTool | FastMCPTool] | None = None,
        tool_choice: ToolChoice | None = None,
        max_iterations: int = 10,
        result_type: type[ResultT],
    ) -> SamplingResult[ResultT]:
        """Overload: With result_type, returns SamplingResult[ResultT]."""

    @overload
    async def sample(
        self,
        messages: str | Sequence[str | SamplingMessage],
        *,
        system_prompt: str | None = None,
        include_context: IncludeContext | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_preferences: ModelPreferences | str | list[str] | None = None,
        tools: Sequence[SamplingTool | FastMCPTool] | None = None,
        tool_choice: ToolChoice | None = None,
        max_iterations: int = 10,
        result_type: None = None,
    ) -> SamplingResult[str]:
        """Overload: Without result_type, returns SamplingResult[str]."""

    async def sample(
        self,
        messages: str | Sequence[str | SamplingMessage],
        *,
        system_prompt: str | None = None,
        include_context: IncludeContext | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_preferences: ModelPreferences | str | list[str] | None = None,
        tools: Sequence[SamplingTool | FastMCPTool] | None = None,
        tool_choice: ToolChoice | None = None,
        max_iterations: int = 10,
        result_type: type[ResultT] | None = None,
    ) -> SamplingResult[ResultT] | SamplingResult[str]:
        """
        Send a sampling request to the client and await the response.

        Call this method at any time to have the server request an LLM
        completion from the client. The client must be appropriately configured,
        or the request will error.

        When tools are provided, the method automatically executes a tool loop:
        if the LLM returns a tool use request, the tools are executed and the
        results are sent back to the LLM. This continues until the LLM provides
        a final response or max_iterations is reached.

        When result_type is specified (not str), a synthetic `final_response` tool
        is created. The LLM calls this tool to provide the structured response,
        which is validated against the result_type and returned as `.result`.

        Args:
            messages: The message(s) to send. Can be a string, list of strings,
                or list of SamplingMessage objects.
            system_prompt: Optional system prompt for the LLM.
            include_context: Optional context inclusion setting.
            temperature: Optional sampling temperature.
            max_tokens: Maximum tokens to generate. Defaults to 512.
            model_preferences: Optional model preferences.
            tools: Optional list of tools the LLM can use. Accepts both
                SamplingTools and FastMCP Tools (which are auto-converted).
                When provided, the method automatically handles tool execution
                and returns the final response after all tool calls complete.
            tool_choice: Optional control over tool usage behavior. Only valid
                when tools are provided.
            max_iterations: Maximum number of LLM calls before returning.
                Defaults to 10. Set to 1 for single-iteration mode where you
                can build your own loop using the history.
            result_type: Optional type for structured output. When specified,
                a synthetic `final_response` tool is created and the LLM's
                response is validated against this type.

        Returns:
            SamplingResult[T] containing:
            - .text: The text representation (raw text or JSON for structured)
            - .result: The typed result (str for text, parsed object for structured)
            - .history: All messages exchanged during sampling
        """

        if max_tokens is None:
            max_tokens = 512

        if isinstance(messages, str):
            sampling_messages = [
                SamplingMessage(
                    content=TextContent(text=messages, type="text"), role="user"
                )
            ]
        elif isinstance(messages, Sequence):
            sampling_messages = [
                SamplingMessage(content=TextContent(text=m, type="text"), role="user")
                if isinstance(m, str)
                else m
                for m in messages
            ]

        # Convert tools to SamplingTools, then to SDK tools
        sampling_tools: list[SamplingTool] = []
        if tools is not None:
            for t in tools:
                if isinstance(t, SamplingTool):
                    sampling_tools.append(t)
                elif isinstance(t, FastMCPTool):
                    sampling_tools.append(SamplingTool.from_mcp_tool(t))
                else:
                    raise TypeError(
                        f"Expected SamplingTool or FastMCP Tool, got {type(t)}"
                    )

        # Create synthetic final_response tool for structured output
        final_response_tool: SamplingTool | None = None
        if result_type is not None and result_type is not str:
            final_response_tool = _create_final_response_tool(result_type)
            sampling_tools.append(final_response_tool)

            # Add hint to system prompt
            hint = "Call final_response when you have completed the task."
            system_prompt = f"{system_prompt}\n\n{hint}" if system_prompt else hint

        sdk_tools: list[SDKTool] | None = None
        if sampling_tools:
            sdk_tools = [t._to_sdk_tool() for t in sampling_tools]

        # Build a tool lookup for execution
        tool_map: dict[str, SamplingTool] = {}
        if sampling_tools:
            tool_map = {t.name: t for t in sampling_tools}

        should_fallback = (
            self.fastmcp.sampling_handler_behavior == "fallback"
            and not self.session.check_client_capability(
                capability=ClientCapabilities(sampling=SamplingCapability())
            )
        )

        if self.fastmcp.sampling_handler_behavior == "always" or should_fallback:
            if self.fastmcp.sampling_handler is None:
                raise ValueError("Client does not support sampling")

            return await self._sample_with_fallback_handler(
                sampling_messages=sampling_messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model_preferences=model_preferences,
                sdk_tools=sdk_tools,
                tool_choice=tool_choice,
                tool_map=tool_map,
                max_iterations=max_iterations,
                result_type=result_type,
                final_response_tool=final_response_tool,
            )

        # When tools are provided, we need the client to support sampling.tools
        if sampling_tools:
            has_tools_capability = self.session.check_client_capability(
                capability=ClientCapabilities(
                    sampling=SamplingCapability(tools=SamplingToolsCapability())
                )
            )
            if not has_tools_capability:
                raise ValueError(
                    "Client does not support sampling with tools. "
                    "The client must advertise the sampling.tools capability."
                )

            return await self._sample_with_client(
                sampling_messages=sampling_messages,
                system_prompt=system_prompt,
                include_context=include_context,
                temperature=temperature,
                max_tokens=max_tokens,
                model_preferences=model_preferences,
                sdk_tools=sdk_tools,
                tool_choice=tool_choice,
                tool_map=tool_map,
                max_iterations=max_iterations,
                result_type=result_type,
                final_response_tool=final_response_tool,
            )

        # Simple case: no tools, no structured output
        result = await self.session.create_message(
            messages=sampling_messages,
            system_prompt=system_prompt,
            include_context=include_context,
            temperature=temperature,
            max_tokens=max_tokens,
            model_preferences=_parse_model_preferences(model_preferences),
            related_request_id=self.request_id,
        )

        # Extract text from content
        text = _extract_text_from_content(result.content)

        return SamplingResult(
            text=text,
            result=cast(ResultT, text),
            history=list(sampling_messages),
        )

    async def _sample_with_fallback_handler(
        self,
        sampling_messages: list[SamplingMessage],
        system_prompt: str | None,
        temperature: float | None,
        max_tokens: int,
        model_preferences: ModelPreferences | str | list[str] | None,
        sdk_tools: list[SDKTool] | None,
        tool_choice: ToolChoice | None,
        tool_map: dict[str, SamplingTool],
        max_iterations: int,
        result_type: type[ResultT] | None,
        final_response_tool: SamplingTool | None,
    ) -> SamplingResult[ResultT] | SamplingResult[str]:
        """Execute sampling with fallback handler, including automatic tool loop."""
        assert self.fastmcp.sampling_handler is not None

        current_messages = list(sampling_messages)
        iteration = 0
        has_tools = bool(sdk_tools)
        has_result_type = result_type is not None and result_type is not str

        while True:
            # On last iteration, force completion
            effective_tool_choice = tool_choice
            if iteration == max_iterations - 1:
                if has_result_type and final_response_tool is not None:
                    # Force final_response tool on last iteration
                    effective_tool_choice = ToolChoice(
                        mode="required", name="final_response"
                    )
                elif has_tools:
                    # Force text response (no tools) on last iteration
                    effective_tool_choice = ToolChoice(mode="none")

            create_message_result = self.fastmcp.sampling_handler(
                current_messages,
                SamplingParams(
                    systemPrompt=system_prompt,
                    messages=current_messages,
                    temperature=temperature,
                    maxTokens=max_tokens,
                    modelPreferences=_parse_model_preferences(model_preferences),
                    tools=sdk_tools,
                    toolChoice=effective_tool_choice,
                ),
                self.request_context,
            )

            if inspect.isawaitable(create_message_result):
                create_message_result = await create_message_result

            iteration += 1

            # Handle simple string/content responses
            if isinstance(create_message_result, str):
                if has_tools:
                    raise ValueError(
                        "Sampling handler returned a string, but tools were provided. "
                        "Handler must return CreateMessageResultWithTools when tools are used."
                    )
                return SamplingResult(
                    text=create_message_result,
                    result=cast(ResultT, create_message_result),
                    history=current_messages,
                )

            if isinstance(create_message_result, CreateMessageResult):
                if has_tools:
                    raise ValueError(
                        "Sampling handler returned CreateMessageResult, but tools were provided. "
                        "Handler must return CreateMessageResultWithTools when tools are used."
                    )
                text = _extract_text_from_content(create_message_result.content)
                return SamplingResult(
                    text=text,
                    result=cast(ResultT, text),
                    history=current_messages,
                )

            if isinstance(create_message_result, CreateMessageResultWithTools):
                # If not a tool use, this is the final response
                if create_message_result.stopReason != "toolUse" or not tool_map:
                    text = _extract_text_from_content(create_message_result.content)
                    return SamplingResult(
                        text=text,
                        result=cast(ResultT, text),
                        history=current_messages,
                    )

                # Check if we've hit max iterations
                if iteration >= max_iterations:
                    # Return what we have with None text (tool use without completion)
                    return SamplingResult(
                        text=None,
                        result=cast(ResultT, None),
                        history=current_messages,
                    )

                # Execute tool calls
                result = await self._execute_tool_calls(
                    result=create_message_result,
                    current_messages=current_messages,
                    tool_map=tool_map,
                    result_type=result_type,
                    final_response_tool=final_response_tool,
                )

                if isinstance(result, SamplingResult):
                    # final_response was called, return the structured result
                    return result

                # result is a tuple of (messages, should_continue)
                current_messages = cast(list[SamplingMessage], result[0])
                should_continue = result[1]
                if not should_continue:
                    text = _extract_text_from_content(create_message_result.content)
                    return SamplingResult(
                        text=text,
                        result=cast(ResultT, text),
                        history=current_messages,
                    )
                continue

            raise ValueError(
                f"Unexpected sampling handler result: {create_message_result}"
            )

    async def _sample_with_client(
        self,
        sampling_messages: list[SamplingMessage],
        system_prompt: str | None,
        include_context: IncludeContext | None,
        temperature: float | None,
        max_tokens: int,
        model_preferences: ModelPreferences | str | list[str] | None,
        sdk_tools: list[SDKTool] | None,
        tool_choice: ToolChoice | None,
        tool_map: dict[str, SamplingTool],
        max_iterations: int,
        result_type: type[ResultT] | None,
        final_response_tool: SamplingTool | None,
    ) -> SamplingResult[ResultT] | SamplingResult[str]:
        """Execute sampling with client, including automatic tool loop."""
        current_messages = list(sampling_messages)
        iteration = 0
        has_tools = bool(sdk_tools)
        has_result_type = result_type is not None and result_type is not str

        while True:
            # On last iteration, force completion
            effective_tool_choice = tool_choice
            if iteration == max_iterations - 1:
                if has_result_type and final_response_tool is not None:
                    # Force final_response tool on last iteration
                    effective_tool_choice = ToolChoice(
                        mode="required", name="final_response"
                    )
                elif has_tools:
                    # Force text response (no tools) on last iteration
                    effective_tool_choice = ToolChoice(mode="none")

            result = await self.session.create_message(
                messages=current_messages,
                system_prompt=system_prompt,
                include_context=include_context,
                temperature=temperature,
                max_tokens=max_tokens,
                model_preferences=_parse_model_preferences(model_preferences),
                tools=sdk_tools,
                tool_choice=effective_tool_choice,
                related_request_id=self.request_id,
            )
            iteration += 1

            # If not a tool use or no tools to execute, return text result
            if result.stopReason != "toolUse" or not tool_map:
                text = _extract_text_from_content(result.content)
                return SamplingResult(
                    text=text,
                    result=cast(ResultT, text),
                    history=current_messages,
                )

            # Check if we've hit max iterations
            if iteration >= max_iterations:
                # Return what we have with None text (tool use without completion)
                return SamplingResult(
                    text=None,
                    result=cast(ResultT, None),
                    history=current_messages,
                )

            # Execute tool calls
            tool_result = await self._execute_tool_calls(
                result=result,
                current_messages=current_messages,
                tool_map=tool_map,
                result_type=result_type,
                final_response_tool=final_response_tool,
            )

            if isinstance(tool_result, SamplingResult):
                # final_response was called, return the structured result
                return tool_result

            # tool_result is a tuple of (messages, should_continue)
            current_messages = cast(list[SamplingMessage], tool_result[0])
            should_continue = tool_result[1]
            if not should_continue:
                text = _extract_text_from_content(result.content)
                return SamplingResult(
                    text=text,
                    result=cast(ResultT, text),
                    history=current_messages,
                )

    async def _execute_tool_calls(
        self,
        result: CreateMessageResultWithTools,
        current_messages: list[SamplingMessage],
        tool_map: dict[str, SamplingTool],
        result_type: type[ResultT] | None,
        final_response_tool: SamplingTool | None,
    ) -> (
        tuple[list[SamplingMessage], bool]
        | SamplingResult[ResultT]
        | SamplingResult[str]
    ):
        """Execute tool calls from an LLM response and return updated messages.

        Returns:
            - Tuple of (updated_messages, should_continue) for normal tool calls
            - SamplingResult when final_response tool is called with valid input
        """
        # Find all tool use content blocks
        content_list = (
            result.content if isinstance(result.content, list) else [result.content]
        )
        tool_use_blocks = [c for c in content_list if isinstance(c, ToolUseContent)]

        if not tool_use_blocks:
            return current_messages, False

        # Add the assistant's response to messages
        current_messages.append(
            SamplingMessage(role="assistant", content=result.content)
        )

        # Execute each tool and collect results
        for tool_use in tool_use_blocks:
            # Check if this is the final_response tool
            if (
                tool_use.name == "final_response"
                and final_response_tool is not None
                and result_type is not None
                and result_type is not str
            ):
                # Validate and parse the input as the result type
                try:
                    type_adapter = get_cached_typeadapter(result_type)
                    validated_result = type_adapter.validate_python(tool_use.input)
                    # Convert to JSON for .text
                    text = json.dumps(
                        type_adapter.dump_python(validated_result, mode="json")
                    )
                    return SamplingResult(
                        text=text,
                        result=validated_result,
                        history=current_messages,
                    )
                except Exception as e:
                    # Validation failed - add error and continue the loop
                    tool_result = ToolResultContent(
                        type="tool_result",
                        toolUseId=tool_use.id,
                        content=[
                            TextContent(
                                type="text",
                                text=f"Validation error: {e}. Please try again.",
                            )
                        ],
                        isError=True,
                    )
                    current_messages.append(
                        SamplingMessage(role="user", content=tool_result)
                    )
                    continue

            tool = tool_map.get(tool_use.name)
            if tool is None:
                # Tool not found - add error result
                tool_result = ToolResultContent(
                    type="tool_result",
                    toolUseId=tool_use.id,
                    content=[
                        TextContent(
                            type="text", text=f"Error: Unknown tool '{tool_use.name}'"
                        )
                    ],
                    isError=True,
                )
            else:
                try:
                    result_value = await tool.run(tool_use.input)
                    tool_result = ToolResultContent(
                        type="tool_result",
                        toolUseId=tool_use.id,
                        content=[TextContent(type="text", text=str(result_value))],
                    )
                except Exception as e:
                    tool_result = ToolResultContent(
                        type="tool_result",
                        toolUseId=tool_use.id,
                        content=[TextContent(type="text", text=f"Error: {e}")],
                        isError=True,
                    )

            # Add tool result to messages
            current_messages.append(SamplingMessage(role="user", content=tool_result))

        return current_messages, True

    @overload
    async def elicit(
        self,
        message: str,
        response_type: None,
    ) -> (
        AcceptedElicitation[dict[str, Any]] | DeclinedElicitation | CancelledElicitation
    ): ...

    """When response_type is None, the accepted elicitation will contain an
    empty dict"""

    @overload
    async def elicit(
        self,
        message: str,
        response_type: type[T],
    ) -> AcceptedElicitation[T] | DeclinedElicitation | CancelledElicitation: ...

    """When response_type is not None, the accepted elicitation will contain the
    response data"""

    @overload
    async def elicit(
        self,
        message: str,
        response_type: list[str],
    ) -> AcceptedElicitation[str] | DeclinedElicitation | CancelledElicitation: ...

    """When response_type is a list of strings, the accepted elicitation will
    contain the selected string response"""

    async def elicit(
        self,
        message: str,
        response_type: type[T] | list[str] | dict[str, dict[str, str]] | None = None,
    ) -> (
        AcceptedElicitation[T]
        | AcceptedElicitation[dict[str, Any]]
        | AcceptedElicitation[str]
        | AcceptedElicitation[list[str]]
        | DeclinedElicitation
        | CancelledElicitation
    ):
        """
        Send an elicitation request to the client and await the response.

        Call this method at any time to request additional information from
        the user through the client. The client must support elicitation,
        or the request will error.

        Note that the MCP protocol only supports simple object schemas with
        primitive types. You can provide a dataclass, TypedDict, or BaseModel to
        comply. If you provide a primitive type, an object schema with a single
        "value" field will be generated for the MCP interaction and
        automatically deconstructed into the primitive type upon response.

        If the response_type is None, the generated schema will be that of an
        empty object in order to comply with the MCP protocol requirements.
        Clients must send an empty object ("{}")in response.

        Args:
            message: A human-readable message explaining what information is needed
            response_type: The type of the response, which should be a primitive
                type or dataclass or BaseModel. If it is a primitive type, an
                object schema with a single "value" field will be generated.
        """
        if response_type is None:
            schema = {"type": "object", "properties": {}}
        else:
            # if the user provided a list of strings, treat it as a Literal
            if isinstance(response_type, list):
                if not all(isinstance(item, str) for item in response_type):
                    raise ValueError(
                        "List of options must be a list of strings. Received: "
                        f"{response_type}"
                    )
                # Convert list of options to Literal type and wrap
                choice_literal = Literal[tuple(response_type)]  # type: ignore
                response_type = ScalarElicitationType[choice_literal]  # type: ignore
            # if the user provided a primitive scalar, wrap it in an object schema
            elif (
                response_type in {bool, int, float, str}
                or get_origin(response_type) is Literal
                or (isinstance(response_type, type) and issubclass(response_type, Enum))
            ):
                response_type = ScalarElicitationType[response_type]  # type: ignore

            response_type = cast(type[T], response_type)

            schema = get_elicitation_schema(response_type)

        result = await self.session.elicit(
            message=message,
            requestedSchema=schema,
            related_request_id=self.request_id,
        )

        if result.action == "accept":
            if response_type is not None:
                # Handle dict-based enum responses (direct value extraction)
                if isinstance(response_type, dict):
                    # Single-select: result.content is {"value": "selected_value"}
                    value = result.content.get("value") if result.content else None
                    return AcceptedElicitation[str](data=cast(str, value))
                elif isinstance(response_type, list) and len(response_type) == 1:
                    if isinstance(response_type[0], dict):
                        # Multi-select titled: result.content is {"value": ["selected1", "selected2"]}
                        value = result.content.get("value") if result.content else None
                        return AcceptedElicitation[list[str]](
                            data=cast(list[str], value)
                        )
                    elif isinstance(response_type[0], list):
                        # Multi-select untitled: result.content is {"value": ["selected1", "selected2"]}
                        value = result.content.get("value") if result.content else None
                        return AcceptedElicitation[list[str]](
                            data=cast(list[str], value)
                        )

                type_adapter = get_cached_typeadapter(response_type)
                validated_data = cast(
                    T | ScalarElicitationType[T],
                    type_adapter.validate_python(result.content),
                )
                if isinstance(validated_data, ScalarElicitationType):
                    return AcceptedElicitation[T](data=validated_data.value)
                else:
                    return AcceptedElicitation[T](data=cast(T, validated_data))
            elif result.content:
                raise ValueError(
                    "Elicitation expected an empty response, but received: "
                    f"{result.content}"
                )
            else:
                return AcceptedElicitation[dict[str, Any]](data={})
        elif result.action == "decline":
            return DeclinedElicitation()
        elif result.action == "cancel":
            return CancelledElicitation()
        else:
            # This should never happen, but handle it just in case
            raise ValueError(f"Unexpected elicitation action: {result.action}")

    def set_state(self, key: str, value: Any) -> None:
        """Set a value in the context state."""
        self._state[key] = value

    def get_state(self, key: str) -> Any:
        """Get a value from the context state. Returns None if the key is not found."""
        return self._state.get(key)

    def _queue_tool_list_changed(self) -> None:
        """Queue a tool list changed notification."""
        self._notification_queue.add("notifications/tools/list_changed")

    def _queue_resource_list_changed(self) -> None:
        """Queue a resource list changed notification."""
        self._notification_queue.add("notifications/resources/list_changed")

    def _queue_prompt_list_changed(self) -> None:
        """Queue a prompt list changed notification."""
        self._notification_queue.add("notifications/prompts/list_changed")

    async def _flush_notifications(self) -> None:
        """Send all queued notifications."""
        async with _flush_lock:
            if not self._notification_queue:
                return

            try:
                if "notifications/tools/list_changed" in self._notification_queue:
                    await self.session.send_tool_list_changed()
                if "notifications/resources/list_changed" in self._notification_queue:
                    await self.session.send_resource_list_changed()
                if "notifications/prompts/list_changed" in self._notification_queue:
                    await self.session.send_prompt_list_changed()
                self._notification_queue.clear()
            except Exception:
                # Don't let notification failures break the request
                pass


def _parse_model_preferences(
    model_preferences: ModelPreferences | str | list[str] | None,
) -> ModelPreferences | None:
    """
    Validates and converts user input for model_preferences into a ModelPreferences object.

    Args:
        model_preferences (ModelPreferences | str | list[str] | None):
            The model preferences to use. Accepts:
            - ModelPreferences (returns as-is)
            - str (single model hint)
            - list[str] (multiple model hints)
            - None (no preferences)

    Returns:
        ModelPreferences | None: The parsed ModelPreferences object, or None if not provided.

    Raises:
        ValueError: If the input is not a supported type or contains invalid values.
    """
    if model_preferences is None:
        return None
    elif isinstance(model_preferences, ModelPreferences):
        return model_preferences
    elif isinstance(model_preferences, str):
        # Single model hint
        return ModelPreferences(hints=[ModelHint(name=model_preferences)])
    elif isinstance(model_preferences, list):
        # List of model hints (strings)
        if not all(isinstance(h, str) for h in model_preferences):
            raise ValueError(
                "All elements of model_preferences list must be"
                " strings (model name hints)."
            )
        return ModelPreferences(hints=[ModelHint(name=h) for h in model_preferences])
    else:
        raise ValueError(
            "model_preferences must be one of: ModelPreferences, str, list[str], or None."
        )


async def _log_to_server_and_client(
    data: LogData,
    session: ServerSession,
    level: LoggingLevel,
    logger_name: str | None = None,
    related_request_id: str | None = None,
) -> None:
    """Log a message to the server and client."""

    msg_prefix = f"Sending {level.upper()} to client"

    if logger_name:
        msg_prefix += f" ({logger_name})"

    to_client_logger.log(
        level=_mcp_level_to_python_level[level],
        msg=f"{msg_prefix}: {data.msg}",
        extra=data.extra,
    )

    await session.send_log_message(
        level=level,
        data=data,
        logger=logger_name,
        related_request_id=related_request_id,
    )


def _create_final_response_tool(result_type: type) -> SamplingTool:
    """Create a synthetic 'final_response' tool for structured output.

    This tool is used to capture structured responses from the LLM.
    The tool's schema is derived from the result_type.
    """
    type_adapter = get_cached_typeadapter(result_type)
    schema = type_adapter.json_schema()
    schema = compress_schema(schema, prune_titles=True)

    # The fn just returns the input as-is (validation happens in the loop)
    def final_response(**kwargs: Any) -> dict[str, Any]:
        return kwargs

    return SamplingTool(
        name="final_response",
        description=(
            "Call this tool to provide your final response. "
            "Use this when you have completed the task and are ready to return the result."
        ),
        parameters=schema,
        fn=final_response,
    )


def _extract_text_from_content(
    content: SamplingMessageContentBlock | list[SamplingMessageContentBlock],
) -> str | None:
    """Extract text from content block(s).

    Returns the text if content is a TextContent or list containing TextContent,
    otherwise returns None.
    """
    if isinstance(content, list):
        for block in content:
            if hasattr(block, "text"):
                return block.text
        return None
    elif hasattr(content, "text"):
        return content.text
    return None
