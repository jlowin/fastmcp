# Distributed TaskContext Design (Redis Pub/Sub)

> **Status**: Design proposal for extending TaskContext to distributed workers

## Problem

The current `TaskContext` implementation only works in **embedded worker mode** because it relies on direct in-process access to `ServerSession` via weakref. Distributed workers (separate processes/machines) cannot access the session object.

## Proposed Solution: Redis Pub/Sub Bridge

Use Docket's existing Redis connection as a bidirectional message channel between distributed workers and the FastMCP server.

> **Note on Reliability**: Redis Pub/Sub is a "fire and forget" mechanism—messages are not persisted. If a subscriber disconnects momentarily, messages published during that window are lost. This design relies on request-level timeouts to detect such failures. For stronger delivery guarantees, a future iteration could use Redis Streams with consumer groups (see Phase 4 in Migration Path).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastMCP Server Process                          │
│  ┌───────────────┐    ┌──────────────────┐    ┌────────────────────┐   │
│  │ ServerSession │◀──▶│ ElicitForwarder  │◀──▶│   Redis Pub/Sub    │   │
│  │  (MCP client) │    │ (background task)│    │                    │   │
│  └───────────────┘    └──────────────────┘    └────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                                         ▲
                                                         │
                                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Distributed Worker Process                         │
│  ┌───────────────┐    ┌──────────────────┐    ┌────────────────────┐   │
│  │  TaskContext  │───▶│ RedisElicitProxy │◀──▶│   Redis Pub/Sub    │   │
│  │   .elicit()   │    │                  │    │                    │   │
│  └───────────────┘    └──────────────────┘    └────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Redis Channel Design

### Channels

```
fastmcp:elicit:{session_id}:{task_id}:request   # Worker → Server
fastmcp:elicit:{session_id}:{task_id}:response  # Server → Worker
fastmcp:sample:{session_id}:{task_id}:request   # Worker → Server
fastmcp:sample:{session_id}:{task_id}:response  # Server → Worker
```

### Message Formats

**Elicitation Request** (Worker → Server):
```json
{
  "request_id": "uuid",
  "message": "Please clarify your query:",
  "schema": { "type": "object", "properties": {...} },
  "timestamp": "2026-01-18T12:00:00Z"
}
```

**Elicitation Response** (Server → Worker):
```json
{
  "request_id": "uuid",
  "action": "accept",
  "content": { "option": "value" },
  "timestamp": "2026-01-18T12:00:01Z"
}
```

**Sampling Request** (Worker → Server):
```json
{
  "request_id": "uuid",
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 500,
  "system_prompt": null,
  "temperature": null,
  "timestamp": "2026-01-18T12:00:00Z"
}
```

**Sampling Response** (Server → Worker):
```json
{
  "request_id": "uuid",
  "result": {
    "role": "assistant",
    "content": {"type": "text", "text": "..."},
    "model": "gpt-4",
    "stopReason": "endTurn"
  },
  "timestamp": "2026-01-18T12:00:02Z"
}
```

> The `result` field contains the full `CreateMessageResult` from the MCP SDK, matching what the worker's `send_sample_via_redis()` expects.

## Implementation

### 1. Mode Detection

```python
# src/fastmcp/server/dependencies.py

def is_embedded_worker() -> bool:
    """Check if running in embedded worker (same process as server)."""
    # Embedded workers have session available via weakref
    task_info = get_task_context()
    if task_info is None:
        return False
    return get_task_session(task_info.session_id) is not None
```

### 2. Redis Elicit Proxy (Worker Side)

```python
# src/fastmcp/server/tasks/redis_proxy.py
"""Redis-based proxy for TaskContext operations in distributed workers."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docket import Docket

# Timeout for waiting for responses (should be configurable)
ELICIT_TIMEOUT_SECONDS = 300  # 5 minutes
SAMPLE_TIMEOUT_SECONDS = 120  # 2 minutes


@dataclass
class ElicitRequest:
    request_id: str
    message: str
    schema: dict[str, Any]
    task_id: str
    session_id: str


@dataclass
class ElicitResponse:
    request_id: str
    action: str  # "accept", "decline", "cancel"
    content: dict[str, Any] | None


async def send_elicit_via_redis(
    docket: Docket,
    session_id: str,
    task_id: str,
    message: str,
    schema: dict[str, Any],
    timeout: float = ELICIT_TIMEOUT_SECONDS,
) -> ElicitResponse:
    """Send elicitation request via Redis and wait for response.
    
    This is used by distributed workers that cannot directly access
    the ServerSession.
    
    Args:
        docket: Docket instance with Redis connection
        session_id: The session ID for this task
        task_id: The MCP task ID
        message: The elicitation message
        schema: The JSON schema for expected response
        timeout: Timeout in seconds
        
    Returns:
        ElicitResponse with action and content
        
    Raises:
        TimeoutError: If no response within timeout
        RuntimeError: If Redis connection fails
    """
    request_id = str(uuid.uuid4())
    request_channel = docket.key(f"fastmcp:elicit:{session_id}:{task_id}:request")
    response_channel = docket.key(f"fastmcp:elicit:{session_id}:{task_id}:response")
    
    request_payload = json.dumps({
        "request_id": request_id,
        "message": message,
        "schema": schema,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    async with docket.redis() as redis:
        # Subscribe to response channel BEFORE publishing request
        # to avoid race condition
        pubsub = redis.pubsub()
        await pubsub.subscribe(response_channel)
        
        try:
            # Publish the request
            await redis.publish(request_channel, request_payload)
            
            # Define the listener coroutine
            async def _listen_for_response() -> ElicitResponse:
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                        
                    try:
                        response_data = json.loads(msg["data"])
                    except json.JSONDecodeError:
                        continue
                    
                    # Check if this response is for our request
                    if response_data.get("request_id") != request_id:
                        continue
                    
                    return ElicitResponse(
                        request_id=request_id,
                        action=response_data["action"],
                        content=response_data.get("content"),
                    )
                
                raise RuntimeError("Pub/sub listener ended unexpectedly")
            
            # Wrap entire listener with timeout - this ensures timeout fires
            # even if pubsub.listen() is blocking waiting for messages
            try:
                return await asyncio.wait_for(_listen_for_response(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Elicitation request {request_id} timed out after {timeout}s"
                ) from None
            
        finally:
            await pubsub.unsubscribe(response_channel)
            await pubsub.close()


async def send_sample_via_redis(
    docket: Docket,
    session_id: str,
    task_id: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 512,
    system_prompt: str | None = None,
    temperature: float | None = None,
    timeout: float = SAMPLE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Send sampling request via Redis and wait for response.
    
    Args:
        docket: Docket instance with Redis connection
        session_id: The session ID for this task
        task_id: The MCP task ID
        messages: Sampling messages
        max_tokens: Maximum tokens in response
        system_prompt: Optional system prompt
        temperature: Sampling temperature
        timeout: Timeout in seconds
        
    Returns:
        CreateMessageResult as dict
        
    Raises:
        TimeoutError: If no response within timeout
    """
    request_id = str(uuid.uuid4())
    request_channel = docket.key(f"fastmcp:sample:{session_id}:{task_id}:request")
    response_channel = docket.key(f"fastmcp:sample:{session_id}:{task_id}:response")
    
    request_payload = json.dumps({
        "request_id": request_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "temperature": temperature,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    async with docket.redis() as redis:
        pubsub = redis.pubsub()
        await pubsub.subscribe(response_channel)
        
        try:
            await redis.publish(request_channel, request_payload)
            
            # Define the listener coroutine
            async def _listen_for_response() -> dict[str, Any]:
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                        
                    try:
                        response_data = json.loads(msg["data"])
                    except json.JSONDecodeError:
                        continue
                    
                    if response_data.get("request_id") != request_id:
                        continue
                    
                    # Check for error
                    if "error" in response_data:
                        raise RuntimeError(response_data["error"])
                    
                    return response_data["result"]
                
                raise RuntimeError("Pub/sub listener ended unexpectedly")
            
            # Wrap entire listener with timeout
            try:
                return await asyncio.wait_for(_listen_for_response(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Sampling request {request_id} timed out after {timeout}s"
                ) from None
            
        finally:
            await pubsub.unsubscribe(response_channel)
            await pubsub.close()
```

### 3. Elicit Forwarder (Server Side)

```python
# src/fastmcp/server/tasks/forwarder.py
"""Forwards elicitation/sampling requests from distributed workers to MCP clients."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from docket import Docket
    from mcp.server.session import ServerSession

logger = get_logger(__name__)


class ElicitForwarder:
    """Forwards elicitation requests from Redis to MCP session.
    
    One forwarder runs per active task in the FastMCP server process.
    It subscribes to Redis channels for that task and forwards requests
    to the associated MCP session.
    """
    
    def __init__(
        self,
        session: ServerSession,
        session_id: str,
        task_id: str,
        docket: Docket,
    ) -> None:
        self._session = session
        self._session_id = session_id
        self._task_id = task_id
        self._docket = docket
        self._running = False
        self._task: asyncio.Task | None = None
    
    async def start(self) -> None:
        """Start the forwarder background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.debug(f"Started elicit forwarder for task {self._task_id}")
    
    async def stop(self) -> None:
        """Stop the forwarder."""
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.debug(f"Stopped elicit forwarder for task {self._task_id}")
    
    async def _run(self) -> None:
        """Main loop: subscribe to request channels and forward to session.
        
        Each request is handled in a separate task to avoid head-of-line blocking
        when the MCP client is slow to respond to elicit/sample requests.
        """
        # Store channel names for exact matching (avoids substring collision)
        elicit_request_channel = self._docket.key(
            f"fastmcp:elicit:{self._session_id}:{self._task_id}:request"
        )
        sample_request_channel = self._docket.key(
            f"fastmcp:sample:{self._session_id}:{self._task_id}:request"
        )
        
        # Track spawned handler tasks for cleanup
        handler_tasks: set[asyncio.Task] = set()
        
        async with self._docket.redis() as redis:
            pubsub = redis.pubsub()
            await pubsub.subscribe(elicit_request_channel, sample_request_channel)
            
            try:
                async for msg in pubsub.listen():
                    if not self._running:
                        break
                    
                    if msg["type"] != "message":
                        continue
                    
                    channel = msg["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")
                    
                    try:
                        data = json.loads(msg["data"])
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in channel {channel}")
                        continue
                    
                    # Use exact channel matching to avoid substring collisions
                    # (e.g., if session_id contains "elicit" or "sample")
                    if channel == elicit_request_channel:
                        task = asyncio.create_task(
                            self._handle_elicit_request(redis, data)
                        )
                        handler_tasks.add(task)
                        task.add_done_callback(handler_tasks.discard)
                    elif channel == sample_request_channel:
                        task = asyncio.create_task(
                            self._handle_sample_request(redis, data)
                        )
                        handler_tasks.add(task)
                        task.add_done_callback(handler_tasks.discard)
                        
            finally:
                # Cancel any in-flight handlers on shutdown
                for task in handler_tasks:
                    task.cancel()
                if handler_tasks:
                    await asyncio.gather(*handler_tasks, return_exceptions=True)
                await pubsub.unsubscribe()
                await pubsub.close()
    
    async def _handle_elicit_request(self, redis, data: dict) -> None:
        """Forward elicitation request to MCP session."""
        request_id = data.get("request_id")
        message = data.get("message", "")
        schema = data.get("schema", {})
        
        response_channel = self._docket.key(
            f"fastmcp:elicit:{self._session_id}:{self._task_id}:response"
        )
        
        try:
            # Update task status to input_required
            from fastmcp.server.tasks.subscriptions import (
                send_input_required_notification,
            )
            await send_input_required_notification(
                session=self._session,
                task_id=self._task_id,
                session_id=self._session_id,
                docket=self._docket,
                status="input_required",
            )
            
            # Forward to MCP client
            result = await self._session.elicit(
                message=message,
                requestedSchema=schema,
                related_task_id=self._task_id,
            )
            
            # Send response back via Redis
            response = {
                "request_id": request_id,
                "action": result.action,
                "content": result.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.publish(response_channel, json.dumps(response))
            
        except Exception as e:
            logger.error(f"Elicit forward failed: {e}")
            # Send error response
            response = {
                "request_id": request_id,
                "action": "cancel",
                "content": None,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.publish(response_channel, json.dumps(response))
            
        finally:
            # Restore status to working
            with suppress(Exception):
                await send_input_required_notification(
                    session=self._session,
                    task_id=self._task_id,
                    session_id=self._session_id,
                    docket=self._docket,
                    status="working",
                )
    
    async def _handle_sample_request(self, redis, data: dict) -> None:
        """Forward sampling request to MCP session."""
        request_id = data.get("request_id")
        messages = data.get("messages", [])
        max_tokens = data.get("max_tokens", 512)
        system_prompt = data.get("system_prompt")
        temperature = data.get("temperature")
        
        response_channel = self._docket.key(
            f"fastmcp:sample:{self._session_id}:{self._task_id}:response"
        )
        
        try:
            from mcp.types import SamplingMessage, TextContent
            from fastmcp.server.tasks.subscriptions import (
                send_input_required_notification,
            )
            
            # Update status
            await send_input_required_notification(
                session=self._session,
                task_id=self._task_id,
                session_id=self._session_id,
                docket=self._docket,
                status="input_required",
            )
            
            # Convert messages
            sampling_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, str):
                    content = TextContent(type="text", text=content)
                sampling_messages.append(SamplingMessage(role=role, content=content))
            
            # Forward to MCP client
            result = await self._session.create_message(
                messages=sampling_messages,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                temperature=temperature,
                related_task_id=self._task_id,
            )
            
            # Send response
            response = {
                "request_id": request_id,
                "result": result.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.publish(response_channel, json.dumps(response))
            
        except Exception as e:
            logger.error(f"Sample forward failed: {e}")
            response = {
                "request_id": request_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.publish(response_channel, json.dumps(response))
            
        finally:
            with suppress(Exception):
                await send_input_required_notification(
                    session=self._session,
                    task_id=self._task_id,
                    session_id=self._session_id,
                    docket=self._docket,
                    status="working",
                )


# Registry of active forwarders
_active_forwarders: dict[str, ElicitForwarder] = {}


async def start_forwarder(
    session: ServerSession,
    session_id: str,
    task_id: str,
    docket: Docket,
) -> None:
    """Start an elicit forwarder for a task.
    
    Called when a task is submitted to Docket.
    """
    key = f"{session_id}:{task_id}"
    if key in _active_forwarders:
        return
    
    forwarder = ElicitForwarder(session, session_id, task_id, docket)
    _active_forwarders[key] = forwarder
    await forwarder.start()


async def stop_forwarder(session_id: str, task_id: str) -> None:
    """Stop the elicit forwarder for a task.
    
    Called when a task completes or is cancelled.
    """
    key = f"{session_id}:{task_id}"
    forwarder = _active_forwarders.pop(key, None)
    if forwarder:
        await forwarder.stop()
```

### 4. Modified TaskContext

```python
# Updates to src/fastmcp/server/dependencies.py

class TaskContext:
    """Context for background tasks with elicitation and sampling support.
    
    TaskContext automatically detects whether it's running in embedded or
    distributed worker mode:
    
    - **Embedded mode**: Direct session access via weakref (current impl)
    - **Distributed mode**: Redis pub/sub bridge to server process
    
    The API is identical in both modes.
    """
    
    __slots__ = ("_task_id", "_session_id", "_distributed")
    
    def __init__(self, task_id: str, session_id: str) -> None:
        self._task_id = task_id
        self._session_id = session_id
        # Detect mode: if session is available, we're embedded
        self._distributed = get_task_session(session_id) is None
    
    @property
    def is_distributed(self) -> bool:
        """True if running in distributed worker mode."""
        return self._distributed
    
    async def elicit(
        self,
        message: str,
        response_type: type | None = None,
    ) -> Any:
        """Request user input, updating task status to input_required."""
        from fastmcp.server.elicitation import parse_elicit_response_type
        
        config = parse_elicit_response_type(response_type)
        
        if self._distributed:
            return await self._elicit_distributed(message, config)
        else:
            return await self._elicit_embedded(message, config)
    
    async def _elicit_embedded(self, message: str, config) -> Any:
        """Elicit via direct session access (embedded mode)."""
        # ... existing implementation ...
        pass
    
    async def _elicit_distributed(self, message: str, config) -> Any:
        """Elicit via Redis pub/sub (distributed mode)."""
        from fastmcp.server.tasks.redis_proxy import send_elicit_via_redis
        from fastmcp.server.elicitation import (
            AcceptedElicitation,
            DeclinedElicitation,
            CancelledElicitation,
            handle_elicit_accept,
        )
        
        docket = self._get_docket()
        
        response = await send_elicit_via_redis(
            docket=docket,
            session_id=self._session_id,
            task_id=self._task_id,
            message=message,
            schema=config.schema,
        )
        
        if response.action == "accept":
            return handle_elicit_accept(config, response.content)
        elif response.action == "decline":
            return DeclinedElicitation()
        else:
            return CancelledElicitation()
    
    async def sample(self, messages: list[Any], **kwargs) -> Any:
        """Request model sampling, updating task status to input_required."""
        if self._distributed:
            return await self._sample_distributed(messages, **kwargs)
        else:
            return await self._sample_embedded(messages, **kwargs)
    
    async def _sample_embedded(self, messages: list[Any], **kwargs) -> Any:
        """Sample via direct session access (embedded mode)."""
        # ... existing implementation ...
        pass
    
    async def _sample_distributed(self, messages: list[Any], **kwargs) -> Any:
        """Sample via Redis pub/sub (distributed mode)."""
        from fastmcp.server.tasks.redis_proxy import send_sample_via_redis
        import mcp.types
        
        docket = self._get_docket()
        
        # Normalize messages to dicts
        normalized = []
        for msg in messages:
            if isinstance(msg, dict):
                normalized.append(msg)
            else:
                normalized.append({
                    "role": getattr(msg, "role", "user"),
                    "content": str(getattr(msg, "content", msg)),
                })
        
        result_dict = await send_sample_via_redis(
            docket=docket,
            session_id=self._session_id,
            task_id=self._task_id,
            messages=normalized,
            max_tokens=kwargs.get("max_tokens", 512),
            system_prompt=kwargs.get("system_prompt"),
            temperature=kwargs.get("temperature"),
        )
        
        return mcp.types.CreateMessageResult.model_validate(result_dict)
```

### 5. Integration with Task Handlers

```python
# Updates to src/fastmcp/server/tasks/handlers.py
import os

async def submit_to_docket(...) -> mcp.types.CreateTaskResult:
    # ... existing code ...
    
    # Register session for TaskContext (embedded mode)
    register_task_session(session_id, ctx.session)
    
    # Start forwarder for distributed mode support (opt-in via feature flag)
    # This runs in the FastMCP server process and listens for Redis messages
    if os.getenv("FASTMCP_DISTRIBUTED_WORKERS", "").lower() == "true":
        from fastmcp.server.tasks.forwarder import start_forwarder
        await start_forwarder(
            session=ctx.session,
            session_id=session_id,
            task_id=server_task_id,
            docket=docket,
        )
    
    # ... rest of implementation ...
```

> **Note on `input_required` for sampling**: SEP-1686 defines `input_required` as the status
> for tasks blocked waiting for client action. While "sampling" requests an LLM response
> (not direct user input), it still requires the client to perform an action before the task
> can proceed. Using `input_required` is semantically correct and consistent with elicitation.
```

### 6. Forwarder Lifecycle Integration with Task Subscriptions

The forwarder must be cleaned up when tasks reach terminal states. This integrates with
the existing `subscribe_to_task_updates()` function in `subscriptions.py`:

```python
# Updates to src/fastmcp/server/tasks/subscriptions.py

async def subscribe_to_task_updates(
    task_id: str,
    task_key: str,
    session: ServerSession,
    docket: Docket,
    poll_interval_ms: int = 5000,
) -> None:
    """Subscribe to Docket execution events and send MCP notifications."""
    try:
        execution = await docket.get_execution(task_key)
        if execution is None:
            logger.warning(f"No execution found for task {task_id}")
            return

        # Extract session_id from task_key for forwarder cleanup
        key_parts = parse_task_key(task_key)
        session_id = key_parts["session_id"]

        async for event in execution.subscribe():
            if event["type"] == "state":
                state = event["state"]
                
                # Send status notification
                await _send_status_notification(
                    session=session,
                    task_id=task_id,
                    task_key=task_key,
                    docket=docket,
                    state=state,
                    poll_interval_ms=poll_interval_ms,
                )
                
                # Clean up forwarder on terminal states
                if state in (
                    ExecutionState.COMPLETED,
                    ExecutionState.FAILED,
                    ExecutionState.CANCELLED,
                ):
                    from fastmcp.server.tasks.forwarder import stop_forwarder
                    await stop_forwarder(session_id, task_id)
                    
            elif event["type"] == "progress":
                await _send_progress_notification(...)

    except Exception as e:
        logger.warning(f"Subscription task failed for {task_id}: {e}", exc_info=True)
        # Also clean up forwarder on subscription failure
        try:
            key_parts = parse_task_key(task_key)
            from fastmcp.server.tasks.forwarder import stop_forwarder
            await stop_forwarder(key_parts["session_id"], task_id)
        except Exception:
            pass
```

### 7. Session Disconnect Handling

When an MCP session disconnects, all associated forwarders must be cleaned up:

```python
# src/fastmcp/server/tasks/forwarder.py - Additional functions

async def stop_forwarders_for_session(session_id: str) -> None:
    """Stop all forwarders for a disconnected session.
    
    Called when an MCP session terminates to clean up resources.
    """
    keys_to_remove = [
        key for key in _active_forwarders
        if key.startswith(f"{session_id}:")
    ]
    
    for key in keys_to_remove:
        forwarder = _active_forwarders.pop(key, None)
        if forwarder:
            await forwarder.stop()
    
    if keys_to_remove:
        logger.debug(f"Stopped {len(keys_to_remove)} forwarders for session {session_id}")


# Integration point: FastMCP server session lifecycle
# In src/fastmcp/server/server.py or session management code:

async def on_session_close(session_id: str) -> None:
    """Called when MCP session closes."""
    from fastmcp.server.tasks.forwarder import stop_forwarders_for_session
    await stop_forwarders_for_session(session_id)
```

## Configuration

```python
# Environment variables
FASTMCP_ELICIT_TIMEOUT = 300      # Seconds to wait for elicitation response
FASTMCP_SAMPLE_TIMEOUT = 120      # Seconds to wait for sampling response
FASTMCP_DISTRIBUTED_WORKERS = true # Enable distributed worker support
```

## Sequence Diagram

```
Worker                     Redis                      FastMCP Server              MCP Client
  │                          │                             │                          │
  │ task_ctx.elicit(msg)     │                             │                          │
  │─────────────────────────▶│                             │                          │
  │                          │ PUBLISH elicit:request      │                          │
  │                          │────────────────────────────▶│                          │
  │                          │                             │ send_input_required()    │
  │                          │                             │─────────────────────────▶│
  │                          │                             │                          │
  │                          │                             │ session.elicit()         │
  │                          │                             │─────────────────────────▶│
  │                          │                             │                          │
  │                          │                             │◀─ ElicitResult ──────────│
  │                          │                             │                          │
  │                          │◀─ PUBLISH elicit:response ──│                          │
  │◀─ ElicitResponse ────────│                             │                          │
  │                          │                             │                          │
  │ return result            │                             │                          │
```

## Testing Strategy

### Unit Tests (Mocked Redis)

```python
# tests/server/tasks/test_redis_proxy.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSendElicitViaRedis:
    """Tests for send_elicit_via_redis()."""
    
    async def test_sends_request_and_receives_response(self):
        """Verify request is published and response is returned."""
        mock_docket = MagicMock()
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        
        # Setup mock pub/sub to return a response
        mock_pubsub.listen.return_value = AsyncIteratorMock([
            {"type": "message", "data": json.dumps({
                "request_id": "test-id",
                "action": "accept",
                "content": {"value": "test"},
            })}
        ])
        mock_redis.pubsub.return_value = mock_pubsub
        mock_docket.redis.return_value.__aenter__.return_value = mock_redis
        mock_docket.key.side_effect = lambda x: x
        
        with patch("uuid.uuid4", return_value="test-id"):
            result = await send_elicit_via_redis(
                docket=mock_docket,
                session_id="session-1",
                task_id="task-1",
                message="Test?",
                schema={"type": "object"},
            )
        
        assert result.action == "accept"
        assert result.content == {"value": "test"}
        mock_redis.publish.assert_called_once()
    
    async def test_timeout_raises_error(self):
        """Verify timeout is properly handled."""
        mock_docket = MagicMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.listen.return_value = AsyncIteratorMock([])  # No response
        
        with pytest.raises(TimeoutError, match="timed out"):
            await send_elicit_via_redis(
                docket=mock_docket,
                session_id="session-1",
                task_id="task-1",
                message="Test?",
                schema={},
                timeout=0.01,  # Very short timeout
            )
    
    async def test_ignores_responses_for_other_requests(self):
        """Verify only matching request_id responses are accepted."""
        # Response with wrong request_id should be ignored
        ...


class TestElicitForwarder:
    """Tests for ElicitForwarder."""
    
    async def test_forwards_elicit_to_session(self):
        """Verify elicitation requests are forwarded to MCP session."""
        mock_session = AsyncMock()
        mock_session.elicit.return_value = MagicMock(
            action="accept", content={"name": "Alice"}
        )
        
        forwarder = ElicitForwarder(
            session=mock_session,
            session_id="session-1",
            task_id="task-1",
            docket=mock_docket,
        )
        
        # Simulate receiving a request
        await forwarder._handle_elicit_request(mock_redis, {
            "request_id": "req-1",
            "message": "Name?",
            "schema": {"type": "object"},
        })
        
        mock_session.elicit.assert_called_once()
        mock_redis.publish.assert_called_once()
    
    async def test_handles_session_elicit_error(self):
        """Verify errors are propagated back via Redis."""
        mock_session = AsyncMock()
        mock_session.elicit.side_effect = Exception("Client error")
        
        forwarder = ElicitForwarder(...)
        await forwarder._handle_elicit_request(mock_redis, {...})
        
        # Should publish error response
        call_args = mock_redis.publish.call_args
        response = json.loads(call_args[0][1])
        assert response["action"] == "cancel"
        assert "error" in response


class TestForwarderLifecycle:
    """Tests for forwarder start/stop."""
    
    async def test_stop_forwarder_cleans_up(self):
        """Verify stop_forwarder removes from registry and stops task."""
        await start_forwarder(session, "s1", "t1", docket)
        assert "s1:t1" in _active_forwarders
        
        await stop_forwarder("s1", "t1")
        assert "s1:t1" not in _active_forwarders
    
    async def test_stop_forwarders_for_session(self):
        """Verify all forwarders for a session are stopped."""
        await start_forwarder(session, "s1", "t1", docket)
        await start_forwarder(session, "s1", "t2", docket)
        await start_forwarder(session, "s2", "t3", docket)
        
        await stop_forwarders_for_session("s1")
        
        assert "s1:t1" not in _active_forwarders
        assert "s1:t2" not in _active_forwarders
        assert "s2:t3" in _active_forwarders  # Different session, still active
```

### Integration Tests (Real Redis)

```python
# tests/server/tasks/test_distributed_elicit_integration.py

import pytest
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="module")
def redis_container():
    """Start Redis container for integration tests."""
    with RedisContainer() as redis:
        yield redis


@pytest.fixture
async def docket_with_redis(redis_container):
    """Create Docket instance connected to test Redis."""
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    async with Docket(url=url) as docket:
        yield docket


class TestDistributedElicitIntegration:
    """Integration tests with real Redis."""
    
    async def test_embedded_vs_distributed_detection(self, docket_with_redis):
        """Verify TaskContext correctly detects embedded vs distributed mode."""
        # With session registered -> embedded
        register_task_session("s1", mock_session)
        ctx = TaskContext("t1", "s1")
        assert ctx.is_distributed is False
        
        # Without session -> distributed
        ctx2 = TaskContext("t2", "s2")  # s2 not registered
        assert ctx2.is_distributed is True
    
    async def test_full_elicit_roundtrip(self, docket_with_redis):
        """Test complete elicit flow through Redis."""
        # Start forwarder in "server" context
        await start_forwarder(mock_session, "s1", "t1", docket_with_redis)
        
        # Simulate distributed worker making elicit call
        response = await send_elicit_via_redis(
            docket=docket_with_redis,
            session_id="s1",
            task_id="t1",
            message="Name?",
            schema={"type": "object", "properties": {"name": {"type": "string"}}},
        )
        
        assert response.action == "accept"
        mock_session.elicit.assert_called_once()
    
    async def test_concurrent_elicitations_same_task(self, docket_with_redis):
        """Verify multiple concurrent elicitations from same task work correctly."""
        await start_forwarder(mock_session, "s1", "t1", docket_with_redis)
        
        # Make 3 concurrent elicit calls
        results = await asyncio.gather(
            send_elicit_via_redis(docket_with_redis, "s1", "t1", "Q1?", {}),
            send_elicit_via_redis(docket_with_redis, "s1", "t1", "Q2?", {}),
            send_elicit_via_redis(docket_with_redis, "s1", "t1", "Q3?", {}),
        )
        
        # Each should get its own response (request_id matching)
        assert len(results) == 3
        assert all(r.action == "accept" for r in results)
```

### Cleanup and Edge Case Tests

```python
class TestCleanupOnTaskCompletion:
    """Verify forwarders are cleaned up on task terminal states."""
    
    async def test_forwarder_stopped_on_task_complete(self):
        """Forwarder stops when task reaches COMPLETED state."""
        ...
    
    async def test_forwarder_stopped_on_task_failed(self):
        """Forwarder stops when task reaches FAILED state."""
        ...
    
    async def test_forwarder_stopped_on_task_cancelled(self):
        """Forwarder stops when task reaches CANCELLED state."""
        ...


class TestSessionDisconnect:
    """Verify cleanup on session disconnect."""
    
    async def test_all_forwarders_stopped_on_session_close(self):
        """All forwarders for a session are stopped when session closes."""
        ...
    
    async def test_other_sessions_unaffected(self):
        """Forwarders for other sessions remain active."""
        ...


class TestRedisConnectionErrors:
    """Verify graceful handling of Redis failures."""
    
    async def test_redis_unavailable_raises_runtime_error(self):
        """Clear error when Redis is unavailable."""
        ...
    
    async def test_redis_disconnect_during_wait(self):
        """Handle Redis disconnect while waiting for response."""
        ...
```

## Migration Path

1. **Phase 1** (current PR): Embedded-only TaskContext
2. **Phase 2**: Add Redis proxy infrastructure (this design)
3. **Phase 3**: Enable distributed mode with feature flag
4. **Phase 4**: Default to distributed-aware mode

## Open Questions - RESOLVED

### 1. Forwarder lifecycle: Should forwarders use task TTL or explicit cleanup?

**Resolution: Explicit cleanup via task subscription terminal states.**

Rationale:
- Task TTL is for result storage, not process lifecycle
- Subscription already tracks state changes (COMPLETED, FAILED, CANCELLED)
- Explicit cleanup is deterministic; TTL-based would leave zombie listeners
- Also need session disconnect cleanup (TTL can't handle this)

Implementation:
```python
# In subscribe_to_task_updates() when state is terminal:
if state in (ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED):
    await stop_forwarder(session_id, task_id)
```

### 2. Error propagation: How to surface Redis connection errors to workers?

**Resolution: Wrap Redis errors in RuntimeError with actionable context.**

```python
# In redis_proxy.py
try:
    async with docket.redis() as redis:
        ...
except RedisError as e:
    raise RuntimeError(
        f"Redis connection failed during distributed elicitation. "
        f"Ensure FASTMCP_DOCKET_URL points to a running Redis instance. "
        f"Original error: {e}"
    ) from e
```

Rationale:
- Users need to know this is a configuration/infrastructure issue
- Original exception preserved via `from e` for debugging
- Specific error class allows callers to handle gracefully if desired

### 3. Backpressure: What if the MCP client is slow to respond?

**Resolution: Request-level timeout with configurable values.**

```python
# Environment-configurable timeouts
FASTMCP_ELICIT_TIMEOUT = int(os.getenv("FASTMCP_ELICIT_TIMEOUT", "300"))  # 5 min default
FASTMCP_SAMPLE_TIMEOUT = int(os.getenv("FASTMCP_SAMPLE_TIMEOUT", "120"))   # 2 min default
```

Rationale:
- Client slowness bounded by timeout (5 min elicit, 2 min sample by default)
- No unbounded waits; worker eventually times out and can fail gracefully
- Long defaults accommodate human-in-the-loop scenarios
- Per-request `timeout` parameter available for fine-grained control

Flow on timeout:
1. Worker's `send_elicit_via_redis()` raises `TimeoutError`
2. Task fails with clear error message
3. Forwarder continues running (may receive late response, but worker already moved on)
4. Forwarder cleaned up when task reaches terminal state

### 4. Security: Should Redis channels require authentication tokens?

**Resolution: Defer to Phase 4; current design relies on Redis ACL + channel isolation.**

Current mitigations:
- Redis connection already authenticated via FASTMCP_DOCKET_URL credentials
- Channel names include `session_id` (opaque UUID) - not guessable
- Workers only know their own task's session_id from execution context

Future enhancement (Phase 4):
- Add HMAC-signed request/response payloads
- Include `worker_id` in requests for audit trail
- Consider Redis Streams with consumer groups for guaranteed delivery

```python
# Future: Signed payloads
import hmac
import hashlib

def sign_payload(payload: dict, secret: str) -> str:
    data = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()

def verify_payload(payload: dict, signature: str, secret: str) -> bool:
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)
```

Rationale for deferring:
- Redis ACL provides baseline security
- Channel name opacity prevents casual enumeration
- Signing adds complexity; evaluate after core functionality proven
- Not blocking for embedded worker users (no Redis involved)
