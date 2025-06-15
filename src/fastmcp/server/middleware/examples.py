"""Example middleware implementations demonstrating the typed middleware system."""

import logging
import time
from typing import Any

from mcp.types import ErrorData, ServerResult

from .base import MCPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(MCPMiddleware):
    """Logs all tool calls with timing."""

    async def on_call_tool_request(self, request, call_next):
        start = time.time()
        tool_name = request.params.name

        logger.info(f"[TOOL CALL] {tool_name} starting...")

        try:
            # Call the actual handler and get the response
            response = await call_next(request)

            # We have access to the response here!
            duration = time.time() - start
            logger.info(f"[TOOL CALL] {tool_name} completed in {duration:.3f}s")

            return response
        except Exception as e:
            duration = time.time() - start
            logger.error(f"[TOOL CALL] {tool_name} failed after {duration:.3f}s: {e}")
            raise


class AuthMiddleware(MCPMiddleware):
    """Checks authorization for resource access."""

    def __init__(self, allowed_prefixes: list[str]):
        self.allowed_prefixes = allowed_prefixes

    def is_authorized(self) -> bool:
        """Check if the current request is authorized."""
        # In a real implementation, this would check tokens, sessions, etc.
        return True  # Placeholder

    async def on_read_resource(self, request, call_next):
        uri = str(request.params.uri)

        # Check if URI is allowed
        if not any(uri.startswith(prefix) for prefix in self.allowed_prefixes):
            # Return error response without calling next
            return ServerResult(
                root=ErrorData(code=403, message=f"Access denied to resource: {uri}")
            )

        # Allowed - continue
        return await call_next(request)


class RateLimitMiddleware(MCPMiddleware):
    """Rate limits all requests."""

    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests = max_requests_per_minute
        self.requests = []

    def is_rate_limited(self) -> bool:
        """Check if current request should be rate limited."""
        now = time.time()
        # Remove requests older than 1 minute
        self.requests = [req_time for req_time in self.requests if now - req_time < 60]

        if len(self.requests) >= self.max_requests:
            return True

        self.requests.append(now)
        return False

    async def on_request(self, request, call_next):
        # Check rate limit here
        if self.is_rate_limited():
            return ServerResult(root=ErrorData(code=429, message="Rate limit exceeded"))

        return await call_next(request)


class ComprehensiveLoggingMiddleware(MCPMiddleware):
    """Logs all MCP activity with detailed information."""

    def __init__(self):
        self.request_count = 0
        self.notification_count = 0

    async def on_request(self, request, call_next):
        """Log all requests."""
        self.request_count += 1
        request_type = type(request).__name__
        request_id = self.request_count

        logger.info(f"[REQUEST #{request_id}] {request_type} starting")
        start = time.time()

        try:
            # Get the response
            response = await call_next(request)

            # Check if it's an error
            if hasattr(response, "root") and isinstance(response.root, ErrorData):
                logger.error(
                    f"[REQUEST #{request_id}] {request_type} failed: "
                    f"{response.root.message} (code: {response.root.code})"
                )
            else:
                duration = time.time() - start
                logger.info(
                    f"[REQUEST #{request_id}] {request_type} completed "
                    f"in {duration:.3f}s"
                )

            return response

        except Exception as e:
            duration = time.time() - start
            logger.error(
                f"[REQUEST #{request_id}] {request_type} raised exception "
                f"after {duration:.3f}s: {e}"
            )
            raise

    async def on_client_notification(self, notification, call_next):
        """Log all notifications."""
        self.notification_count += 1
        notification_type = type(notification).__name__

        logger.info(f"[NOTIFICATION #{self.notification_count}] {notification_type}")

        await call_next(notification)

    async def on_call_tool_request(self, request, call_next):
        """Extra logging for tool calls."""
        tool_name = request.params.name
        args = request.params.arguments

        logger.info(f"  Tool: {tool_name}")
        logger.debug(f"  Arguments: {args}")

        # Still need to call next to continue the chain
        return await call_next(request)

    async def on_progress_notification(self, notification, call_next):
        """Log progress updates."""
        progress = notification.params.progress
        total = (
            notification.params.total if hasattr(notification.params, "total") else None
        )
        message = (
            notification.params.message
            if hasattr(notification.params, "message")
            else None
        )

        if total:
            percent = (progress / total) * 100
            logger.info(f"  Progress: {percent:.1f}% - {message or 'No message'}")
        else:
            logger.info(f"  Progress: {progress} - {message or 'No message'}")

        await call_next(notification)


class ContextTrackingMiddleware(MCPMiddleware):
    """Tracks context across requests and notifications."""

    def __init__(self):
        self.active_requests: dict[str, Any] = {}

    async def on_request(self, request, call_next):
        """Track active requests."""
        try:
            # Get request context if available
            from mcp.server.lowlevel.server import request_ctx

            ctx = request_ctx.get()
            request_id = str(ctx.request_id)
        except:
            # Fallback if context is not available
            request_id = str(id(request))

        # Store request info
        self.active_requests[request_id] = {
            "type": type(request).__name__,
            "start_time": time.time(),
        }

        try:
            response = await call_next(request)
            return response
        finally:
            # Clean up
            if request_id in self.active_requests:
                del self.active_requests[request_id]

    async def on_progress_notification(self, notification, call_next):
        """Link progress to its parent request."""
        progress_token = getattr(notification.params, "progressToken", None)

        if progress_token:
            # Find the request this progress belongs to
            request_info = self.active_requests.get(str(progress_token))
            if request_info:
                elapsed = time.time() - request_info["start_time"]
                logger.info(
                    f"Progress for {request_info['type']} (elapsed: {elapsed:.1f}s)"
                )

        await call_next(notification)


class SelectiveAuthMiddleware(MCPMiddleware):
    """Only requires auth for certain operations."""

    def is_authorized(self) -> bool:
        """Check if the current request is authorized."""
        # In a real implementation, this would check tokens, sessions, etc.
        return False  # Simulating unauthorized for demo

    async def on_call_tool_request(self, request, call_next):
        # Only require auth for dangerous tools
        if request.params.name.startswith("admin_"):
            if not self.is_authorized():
                return ServerResult(
                    root=ErrorData(code=403, message="Admin tools require auth")
                )
        return await call_next(request)

    async def on_read_resource(self, request, call_next):
        # Require auth for all resources
        if not self.is_authorized():
            return ServerResult(
                root=ErrorData(code=403, message="Resources require auth")
            )
        return await call_next(request)
