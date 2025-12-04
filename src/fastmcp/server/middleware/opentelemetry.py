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
    from opentelemetry.context import Context
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

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
        propagate_context: Whether to propagate trace context through MCP _meta fields
            (default: True). When enabled, trace context is injected into response metadata
            and extracted from request metadata, enabling distributed tracing across protocols
            that don't support HTTP headers (like SSE).

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
            max_argument_length=1000,
            propagate_context=True  # Enable trace context propagation
        ))
        ```
    """

    def __init__(
        self,
        tracer_name: str = "fastmcp",
        enabled: bool = True,
        include_arguments: bool = True,
        max_argument_length: int = 500,
        propagate_context: bool = True,
    ):
        """Initialize OpenTelemetry middleware.

        Args:
            tracer_name: Name for the OpenTelemetry tracer
            enabled: Whether to enable tracing
            include_arguments: Whether to include operation arguments as span attributes
            max_argument_length: Maximum length of argument strings in span attributes
            propagate_context: Whether to propagate trace context through MCP _meta fields
        """
        self.enabled = enabled and OPENTELEMETRY_AVAILABLE
        self.include_arguments = include_arguments
        self.max_argument_length = max_argument_length
        self.propagate_context = propagate_context

        if self.enabled:
            self.tracer = trace.get_tracer(tracer_name)
            if self.propagate_context:
                self.propagator = TraceContextTextMapPropagator()
            else:
                self.propagator = None
        else:
            self.tracer = None
            self.propagator = None

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

    def _extract_trace_context(self, context: MiddlewareContext) -> Context | None:
        """Extract trace context from request metadata if available.

        Args:
            context: The middleware context containing the request

        Returns:
            OpenTelemetry Context with extracted trace information, or None if not available
        """
        if not self.propagate_context or not self.propagator:
            return None

        # Get _meta from the request message
        request_meta = getattr(context.message, "_meta", None)
        if not request_meta or not isinstance(request_meta, dict):
            return None

        # Extract trace context using W3C Trace Context format
        try:
            carrier = {}
            if "traceparent" in request_meta:
                carrier["traceparent"] = request_meta["traceparent"]
            if "tracestate" in request_meta:
                carrier["tracestate"] = request_meta["tracestate"]

            if carrier:
                otel_context = self.propagator.extract(carrier=carrier)  # type: ignore[union-attr]
                return otel_context
        except Exception as e:
            logger.debug(f"Failed to extract trace context from metadata: {e}")

        return None

    def _inject_trace_context(self, result: Any) -> Any:
        """Inject current trace context into result metadata.

        Args:
            result: The result to inject trace context into

        Returns:
            Result with trace context injected into _meta field
        """
        if not self.propagate_context or not self.propagator:
            return result

        try:
            # Get current span context
            current_span = trace.get_current_span()
            if not current_span or not current_span.get_span_context().is_valid:
                return result

            # Inject trace context into carrier
            carrier: dict[str, str] = {}
            self.propagator.inject(carrier=carrier)  # type: ignore[union-attr]

            if not carrier:
                return result

            # Add trace context to result metadata
            # Handle different result types
            if hasattr(result, "_meta"):
                # Result already has _meta attribute (like CallToolResult)
                if result._meta is None:
                    result._meta = {}
                result._meta.update(carrier)
            elif hasattr(result, "meta"):
                # Result has meta attribute (like ToolResult)
                if result.meta is None:
                    result.meta = {}
                result.meta.update(carrier)
            else:
                # For list results or other types, we can't inject context
                pass

        except Exception as e:
            logger.debug(f"Failed to inject trace context into metadata: {e}")

        return result

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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

        tool_name = getattr(context.message, "name", "unknown")
        tool_arguments = getattr(context.message, "arguments", {})

        span_attributes = self._create_span_attributes(
            context,
            **{
                "mcp.tool.name": tool_name,
                "mcp.tool.arguments": self._truncate_value(tool_arguments),
            },
        )

        # Start span with parent context if available
        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            f"tool.{tool_name}", attributes=span_attributes, context=parent_context
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.tool.success", True)
                span.set_status(Status(StatusCode.OK))
                # Inject trace context into result
                return self._inject_trace_context(result)
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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

        resource_uri = getattr(context.message, "uri", "unknown")

        span_attributes = self._create_span_attributes(
            context, **{"mcp.resource.uri": resource_uri}
        )

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "resource.read", attributes=span_attributes, context=parent_context
        ) as span:
            try:
                result = await call_next(context)
                span.set_status(Status(StatusCode.OK))
                return self._inject_trace_context(result)
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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

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
            f"prompt.{prompt_name}", attributes=span_attributes, context=parent_context
        ) as span:
            try:
                result = await call_next(context)
                span.set_status(Status(StatusCode.OK))
                return self._inject_trace_context(result)
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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "tools.list", attributes=span_attributes, context=parent_context
        ) as span:
            try:
                result = await call_next(context)
                span.set_attribute("mcp.tools.count", len(result))
                span.set_status(Status(StatusCode.OK))
                # List operations return lists, so we can't inject trace context
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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "resources.list", attributes=span_attributes, context=parent_context
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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "resource_templates.list",
            attributes=span_attributes,
            context=parent_context,
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

        # Extract trace context from request metadata
        parent_context = self._extract_trace_context(context)

        span_attributes = self._create_span_attributes(context)

        with self.tracer.start_as_current_span(  # type: ignore[union-attr]
            "prompts.list", attributes=span_attributes, context=parent_context
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
