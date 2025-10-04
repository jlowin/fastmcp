"""
OpenTelemetry Integration Example

This example demonstrates how to integrate OpenTelemetry with FastMCP for
comprehensive observability. It shows:

1. Configuring OpenTelemetry tracing and logging
2. Creating custom middleware that emits spans
3. Attaching OpenTelemetry to FastMCP's logger
4. Exporting to console (easily switch to OTLP for production)

To run this example:
    uv run examples/opentelemetry_example.py

For production, replace ConsoleSpanExporter/ConsoleLogExporter with:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

Requirements:
    pip install opentelemetry-api opentelemetry-sdk
"""

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.utilities.logging import get_logger

# ============================================================================
# OpenTelemetry Configuration
# ============================================================================

# Define service metadata
resource = Resource(
    attributes={
        "service.name": "fastmcp-weather-server",
        "service.version": "1.0.0",
        "deployment.environment": "development",
    }
)

# Configure tracing
trace_provider = TracerProvider(resource=resource)
trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(trace_provider)

# Configure logging
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))
set_logger_provider(logger_provider)

# ============================================================================
# Custom Middleware for OpenTelemetry Spans
# ============================================================================


class OpenTelemetryMiddleware(Middleware):
    """Middleware that creates OpenTelemetry spans for MCP operations."""

    def __init__(self, tracer_name: str = "fastmcp"):
        self.tracer = trace.get_tracer(tracer_name)

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Create a span for each tool call with detailed attributes."""
        tool_name = context.message.name

        # Create a span for this tool call
        with self.tracer.start_as_current_span(
            f"tool.{tool_name}",
            attributes={
                "mcp.method": context.method,
                "mcp.source": context.source,
                "mcp.tool.name": tool_name,
                "mcp.tool.arguments": str(context.message.arguments),
            },
        ) as span:
            try:
                # Execute the tool
                result = await call_next(context)

                # Mark span as successful
                span.set_attribute("mcp.tool.success", True)
                span.set_status(Status(StatusCode.OK))

                return result

            except Exception as e:
                # Record the error in the span
                span.set_attribute("mcp.tool.success", False)
                span.set_attribute("mcp.tool.error", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise


# ============================================================================
# FastMCP Server Setup
# ============================================================================

# Create FastMCP server
mcp = FastMCP("Weather Server")

# Attach OpenTelemetry to FastMCP's logger
logger = get_logger("weather")
logger.addHandler(LoggingHandler(logger_provider=logger_provider))

# Add OpenTelemetry middleware
mcp.add_middleware(OpenTelemetryMiddleware())

# ============================================================================
# Server Tools
# ============================================================================


@mcp.tool()
def get_weather(city: str) -> dict:
    """Get current weather for a city.

    Args:
        city: Name of the city

    Returns:
        Weather information including temperature and conditions
    """
    logger.info(f"Fetching weather for {city}")

    # Simulate weather lookup
    weather_data = {
        "city": city,
        "temperature": 72,
        "condition": "sunny",
        "humidity": 45,
    }

    logger.info(
        f"Weather retrieved: {weather_data['condition']}, {weather_data['temperature']}°F"
    )

    return weather_data


@mcp.tool()
def get_forecast(city: str, days: int = 3) -> dict:
    """Get weather forecast for a city.

    Args:
        city: Name of the city
        days: Number of days to forecast (1-7)

    Returns:
        Forecast data for the specified number of days
    """
    logger.info(f"Fetching {days}-day forecast for {city}")

    if days < 1 or days > 7:
        logger.warning(f"Invalid days parameter: {days}. Must be 1-7.")
        raise ValueError("Days must be between 1 and 7")

    # Simulate forecast data
    forecast = {
        "city": city,
        "days": days,
        "forecast": [
            {"day": i + 1, "temp": 70 + i, "condition": "partly cloudy"}
            for i in range(days)
        ],
    }

    logger.info(f"Forecast retrieved for {days} days")

    return forecast


@mcp.tool()
def convert_temperature(temp: float, from_unit: str, to_unit: str) -> dict:
    """Convert temperature between Fahrenheit and Celsius.

    Args:
        temp: Temperature value to convert
        from_unit: Source unit ('F' or 'C')
        to_unit: Target unit ('F' or 'C')

    Returns:
        Converted temperature value
    """
    logger.debug(f"Converting {temp}°{from_unit} to °{to_unit}")

    # Validate units
    if from_unit not in ["F", "C"] or to_unit not in ["F", "C"]:
        logger.error(f"Invalid units: {from_unit} or {to_unit}")
        raise ValueError("Units must be 'F' or 'C'")

    # Perform conversion
    if from_unit == to_unit:
        result = temp
    elif from_unit == "F" and to_unit == "C":
        result = (temp - 32) * 5 / 9
    else:  # from_unit == "C" and to_unit == "F"
        result = (temp * 9 / 5) + 32

    logger.info(f"Converted {temp}°{from_unit} to {result:.1f}°{to_unit}")

    return {
        "original": {"value": temp, "unit": from_unit},
        "converted": {"value": round(result, 1), "unit": to_unit},
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("FastMCP + OpenTelemetry Example")
    print("=" * 70)
    print("\nThis example demonstrates OpenTelemetry integration with FastMCP.")
    print("Watch the console for:")
    print("  - Trace spans showing tool execution timing")
    print("  - Log entries from FastMCP's logger")
    print("\nFor production, replace console exporters with OTLP exporters")
    print("to send data to Grafana, Jaeger, or other observability platforms.")
    print("=" * 70)
    print()

    # Run the server
    mcp.run()
