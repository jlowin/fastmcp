"""OpenTelemetry instrumentation middleware for distributed tracing and observability.

This middleware provides automatic OpenTelemetry instrumentation for FastMCP servers,
creating spans for all MCP operations. It gracefully handles the case where OpenTelemetry
is not installed, making it safe to enable by default.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

    mcp = FastMCP("MyServer")
    mcp.add_middleware(OpenTelemetryMiddleware())  # Enabled by default
    ```

    To configure OpenTelemetry, set up providers before creating your server:

    ```python
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    # Configure tracing
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(trace_provider)

    # Now create your FastMCP server
    mcp = FastMCP("MyServer")
    mcp.add_middleware(OpenTelemetryMiddleware())
    ```
"""

import logging
from typing import Any

from .middleware import CallNext, Middleware, MiddlewareContext

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry components
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    logger.debug("OpenTelemetry not available - spans will not be created")


class OpenTelemetryMiddleware(Middleware):
    """Middleware that creates OpenTelemetry spans for MCP operations.

    This middleware automatically instruments FastMCP servers with OpenTelemetry
    distributed tracing. It creates spans for all MCP operations including tool calls,
    resource reads, prompt retrievals, and list operations.

    If OpenTelemetry is not installed, this middleware becomes a no-op, making it
    safe to enable by default without requiring OpenTelemetry as a dependency.

    Args:
        tracer_name: Name for the OpenTelemetry tracer (default: "fastmcp")
        enabled: Whether to enable tracing (default: True)
        include_arguments: Whether to include operation arguments as span attributes
            (default: True). Set to False to avoid including potentially sensitive data.
        max_argument_length: Maximum length of argument strings in span attributes
            (default: 500). Prevents spans from becoming too large.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("MyServer")

        # Enable with default settings
        mcp.add_middleware(OpenTelemetryMiddleware())

        # Or customize the configuration
        mcp.add_middleware(OpenTelemetryMiddleware(
            tracer_name="my-custom-tracer",
            include_arguments=False,  # Don't include arguments for privacy
            max_argument_length=1000
        ))
        ```
    """

    def __init__(
        self,
        tracer_name: str = "fastmcp",
        enabled: bool = True,
        include_arguments: bool = True,
        max_argument_length: int = 500,
    ):
        """Initialize OpenTelemetry middleware.

        Args:
            tracer_name: Name for the OpenTelemetry tracer
            enabled: Whether to enable tracing
            include_arguments: Whether to include operation arguments as span attributes
            max_argument_length: Maximum length of argument strings in span attributes
        """
        self.enabled = enabled and OPENTELEMETRY_AVAILABLE
        self.include_arguments = include_arguments
        self.max_argument_length = max_argument_length

        if self.enabled:
            self.tracer = trace.get_tracer(tracer_name)
        else:
            self.tracer = None

        if not OPENTELEMETRY_AVAILABLE and enabled:
            logger.info(
                "OpenTelemetry middleware is enabled but opentelemetry-api is not installed. "
                "Install with: pip install opentelemetry-api opentelemetry-sdk"
            )

    def _truncate_value(self, value: Any) -> str:
        """Truncate a value to the configured maximum length."""
        str_value = str(value)
        if len(str_value) > self.max_argument_length:
            return str_value[: self.max_argument_length] + "..."
        return str_value

    def _create_span_attributes(self, context: MiddlewareContext, **extra: Any) -> dict:
        """Create span attributes from context and extra parameters."""
        attributes = {
            "mcp.method": context.method or "unknown",
            "mcp.source": context.source,
            "mcp.type": context.type,
        }

        if self.include_arguments:
            attributes.update(extra)

        return attributes

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for tool execution."""
        if not self.enabled:
            return await call_next(context)

        tool_name = getattr(context.message, "name", "unknown")
        tool_arguments = getattr(context.message, "arguments", {})

        span_attributes = self._create_span_attributes(
            context,
            **{
                "mcp.tool.name": tool_name,
                "mcp.tool.arguments": self._truncate_value(tool_arguments),
            },
        )

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            f"tool.{tool_name}", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.tool.success", True)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_attribute("mcp.tool.success", False)
                span.set_attribute("mcp.tool.error", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def on_read_resource(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for resource reading."""
        if not self.enabled:
            return await call_next(context)

        resource_uri = getattr(context.message, "uri", "unknown")

        span_attributes = self._create_span_attributes(
            context, **{"mcp.resource.uri": resource_uri}
        )

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            f"resource.read", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def on_get_prompt(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for prompt retrieval."""
        if not self.enabled:
            return await call_next(context)

        prompt_name = getattr(context.message, "name", "unknown")
        prompt_arguments = getattr(context.message, "arguments", {})

        span_attributes = self._create_span_attributes(
            context,
            **{
                "mcp.prompt.name": prompt_name,
                "mcp.prompt.arguments": self._truncate_value(prompt_arguments),
            },
        )

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            f"prompt.{prompt_name}", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def on_list_tools(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for listing tools."""
        if not self.enabled:
            return await call_next(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "tools.list", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.tools.count", len(result))
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def on_list_resources(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for listing resources."""
        if not self.enabled:
            return await call_next(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "resources.list", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.resources.count", len(result))
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def on_list_resource_templates(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for listing resource templates."""
        if not self.enabled:
            return await call_next(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "resource_templates.list", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.resource_templates.count", len(result))
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def on_list_prompts(
        self, context: MiddlewareContext, call_next: CallNext
    ) -> Any:
        """Create a span for listing prompts."""
        if not self.enabled:
            return await call_next(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "prompts.list", attributes=span_attributes
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.prompts.count", len(result))
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
