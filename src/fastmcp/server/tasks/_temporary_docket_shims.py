"""
⚠️ TEMPORARY CODE - DELETE WHEN DOCKET ISSUES RESOLVED ⚠️

This file emulates Docket features that will become native:
- https://github.com/chrisguidry/docket/issues/167 (Execution state tracking)
- https://github.com/chrisguidry/docket/issues/166 (Execution result storage)
- https://github.com/chrisguidry/docket/issues/88 (Automatic expiration)

Provides temporary task result storage, state tracking, and expiration management
until Docket's Execution objects support native state/result APIs.

DO NOT WRITE TESTS FOR THIS FILE - it will be completely deleted and replaced
with Docket's native APIs:
- Execution.get_state() / Execution.set_state()
- Execution.get_result()
- Automatic expiration handling

When Docket issues are resolved:
1. Delete this entire file
2. Replace calls with Docket's native Execution APIs
3. Remove manual expiration cleanup
"""

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import cloudpickle
from docket import TaskKey

from fastmcp.dependencies import CurrentFastMCP


@dataclass
class TaskResult:
    """Stores the result of a completed task.

    Results are stored as cloudpickle-serialized bytes to match Docket's future behavior.
    Will be replaced by Docket's native result storage in issues #166/#167.
    """

    value_bytes: bytes  # Cloudpickle-serialized result
    error_bytes: bytes | None  # Cloudpickle-serialized exception if failed
    completed_at: datetime
    expires_at: datetime
    keep_alive: int

    @property
    def value(self) -> Any | None:
        """Deserialize and return the value."""
        if self.error_bytes:
            return None
        return cloudpickle.loads(self.value_bytes)

    @property
    def error(self) -> Exception | None:
        """Deserialize and return the error."""
        if self.error_bytes is None:
            return None
        return cloudpickle.loads(self.error_bytes)


# Module-level storage
# Keys are encoded with metadata: {session_id}:{client_task_id}:{task_type}:{component_identifier}
# Will be replaced by Docket's native Execution state/result storage
_task_results: dict[str, TaskResult] = {}
_task_states: dict[str, str] = {}
_task_keep_alive: dict[str, int] = {}  # Maps task_key → keep_alive duration
_lock = asyncio.Lock()


async def set_state(task_key: str, state: str, keep_alive: int | None = None) -> None:
    """Set the current state of a task.

    TODO: Replace with Execution.set_state() when https://github.com/chrisguidry/docket/issues/167 is resolved

    Args:
        task_key: Full task key (includes metadata)
        state: Task state (submitted, working, completed, failed)
        keep_alive: Optional keep_alive to store (needed for result expiration)
    """
    async with _lock:
        _task_states[task_key] = state
        if keep_alive is not None:
            _task_keep_alive[task_key] = keep_alive


async def get_state(task_key: str) -> str | None:
    """Get the current state of a task.

    TODO: Replace with Execution.get_state() when https://github.com/chrisguidry/docket/issues/167 is resolved

    Args:
        task_key: Full task key (includes metadata)

    Returns:
        Task state or None if not found
    """
    async with _lock:
        return _task_states.get(task_key)


async def store_result(task_key: str, value: Any, keep_alive: int) -> None:
    """Store a successful task result with expiration.

    Serializes value with cloudpickle to match Docket's future behavior.

    TODO: Replace with Execution result storage when https://github.com/chrisguidry/docket/issues/166 is resolved

    Args:
        task_key: Full task key (includes metadata)
        value: The task's return value (raw Python value, not MCP types)
        keep_alive: Result retention duration in milliseconds
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"STORE_RESULT: key={task_key[:60]}..., value={value!r}")

    now = datetime.now()
    expires_at = now + timedelta(milliseconds=keep_alive)

    # Serialize with cloudpickle (matches Docket's future behavior)
    try:
        value_bytes = cloudpickle.dumps(value)
        logger.debug(f"STORE_RESULT: Serialized {len(value_bytes)} bytes")
    except Exception as e:
        logger.error(f"STORE_RESULT: Serialization failed: {e}")
        raise

    async with _lock:
        _task_results[task_key] = TaskResult(
            value_bytes=value_bytes,
            error_bytes=None,
            completed_at=now,
            expires_at=expires_at,
            keep_alive=keep_alive,
        )
        _task_states[task_key] = "completed"


async def store_error(task_key: str, error: Exception, keep_alive: int) -> None:
    """Store a failed task error with expiration.

    Serializes exception with cloudpickle to match Docket's future behavior.

    TODO: Replace with Execution result storage when https://github.com/chrisguidry/docket/issues/166 is resolved

    Args:
        task_key: Full task key (includes metadata)
        error: The exception that caused task failure
        keep_alive: Result retention duration in milliseconds
    """
    now = datetime.now()
    expires_at = now + timedelta(milliseconds=keep_alive)

    # Serialize with cloudpickle
    error_bytes = cloudpickle.dumps(error)

    async with _lock:
        _task_results[task_key] = TaskResult(
            value_bytes=b"",  # No value for errors
            error_bytes=error_bytes,
            completed_at=now,
            expires_at=expires_at,
            keep_alive=keep_alive,
        )
        _task_states[task_key] = "failed"


async def get_result(task_key: str) -> TaskResult | None:
    """Retrieve a completed task result.

    TODO: Replace with Execution.get_result() when https://github.com/chrisguidry/docket/issues/166 is resolved

    Args:
        task_key: Full task key (includes metadata)

    Returns:
        TaskResult or None if not found
    """
    async with _lock:
        return _task_results.get(task_key)


async def has_result(task_key: str) -> bool:
    """Check if a task has a result stored.

    Args:
        task_key: Full task key (includes metadata)

    Returns:
        True if result exists
    """
    async with _lock:
        return task_key in _task_results


async def cleanup_expired() -> int:
    """Remove expired task results and states.

    Per SEP-1686, after keepAlive expires following terminal state,
    servers MAY delete the task and all associated data.

    TODO: Replace with Docket's automatic expiration when https://github.com/chrisguidry/docket/issues/88 is resolved

    Returns:
        Number of tasks cleaned up
    """
    now = datetime.now()
    async with _lock:
        expired_keys = [
            task_key
            for task_key, result in _task_results.items()
            if result.expires_at <= now
        ]

        for task_key in expired_keys:
            _task_results.pop(task_key, None)
            _task_states.pop(task_key, None)
            _task_keep_alive.pop(task_key, None)

        return len(expired_keys)


async def cancel_task(task_key: str) -> bool:
    """Cancel a task, transitioning it to cancelled state.

    Uses Docket's native cancel() to stop execution, then sets state to cancelled.
    Unlike delete_task, this preserves the task state for polling.

    TODO: Replace with Docket's native cancellation when available

    Args:
        task_key: Full task key (includes metadata)

    Returns:
        True if task was found and cancelled, False if not found
    """
    from contextlib import suppress

    from fastmcp.server.dependencies import _current_docket

    async with _lock:
        # Check if task exists
        found = task_key in _task_states or task_key in _task_results

        if not found:
            return False

        # Cancel the Docket execution if it's still running
        docket = _current_docket.get()
        if docket is not None:
            with suppress(Exception):
                await docket.cancel(task_key)

        # Set state to cancelled (keep state and results for polling)
        _task_states[task_key] = "cancelled"

        return True


async def delete_task(task_key: str) -> bool:
    """Delete a task and all associated data.

    Uses Docket's native cancel() to stop running tasks, then removes our
    temporary state/result storage.

    Args:
        task_key: Full task key (includes metadata)

    Returns:
        True if task was found and deleted, False if not found
    """
    from contextlib import suppress

    from fastmcp.server.dependencies import _current_docket

    async with _lock:
        found = task_key in _task_states or task_key in _task_results

        if not found:
            return False

        # Cancel the Docket execution if it's still running (uses native Docket API)
        docket = _current_docket.get()
        if docket is not None:
            with suppress(Exception):
                # Task might not exist in Docket or already completed
                await docket.cancel(task_key)

        # Remove all our temporary storage
        _task_states.pop(task_key, None)
        _task_results.pop(task_key, None)
        _task_keep_alive.pop(task_key, None)

        return True


@lru_cache(maxsize=1000)
def wrap_function_for_result_storage(user_fn: Callable) -> Callable:
    """Wrap a user function to automatically store its result.

    Uses Docket's TaskKey() dependency to get the current task's key at runtime.
    This wrapper is cached per user function to avoid Docket's function deduplication issues.

    Args:
        user_fn: The user's tool/prompt/resource function

    Returns:
        Wrapped function that stores result after execution
    """
    # Get user function's signature
    user_sig = inspect.signature(user_fn)

    # Build new parameters: user params + dependency params
    new_params = list(user_sig.parameters.values())

    # Add dependency parameters at the end
    new_params.append(
        inspect.Parameter(
            "__docket_task_key",
            inspect.Parameter.KEYWORD_ONLY,
            default=TaskKey(),
            annotation=str,
        )
    )
    new_params.append(
        inspect.Parameter(
            "__fastmcp_server",
            inspect.Parameter.KEYWORD_ONLY,
            default=CurrentFastMCP(),
            annotation=Any,
        )
    )

    # Create new signature
    new_sig = inspect.Signature(
        new_params, return_annotation=user_sig.return_annotation
    )

    # Create wrapper function
    async def _execute_and_store_result(*args, **kwargs):
        # Extract our injected dependencies from kwargs
        task_key = kwargs.pop("__docket_task_key")
        server = kwargs.pop("__fastmcp_server")

        try:
            # Get keep_alive from storage (set when task was submitted)
            async with _lock:
                keep_alive = _task_keep_alive.get(task_key, 60000)

            await set_state(task_key, "working")

            # Create FastMCP context
            import fastmcp.server.context

            async with fastmcp.server.context.Context(fastmcp=server):
                # Call user function - Docket already injected user's dependencies!
                result = user_fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result

                # Store raw return value
                await store_result(task_key, result, keep_alive)
                return result
        except Exception as e:
            await store_error(task_key, e, keep_alive)
            raise

    # Set signature and metadata
    _execute_and_store_result.__signature__ = new_sig  # type: ignore[attr-defined]
    _execute_and_store_result.__name__ = user_fn.__name__  # type: ignore[attr-defined]
    _execute_and_store_result.__qualname__ = getattr(  # type: ignore[attr-defined]
        user_fn,
        "__qualname__",
        user_fn.__name__,  # type: ignore[attr-defined]
    )
    _execute_and_store_result.__module__ = getattr(user_fn, "__module__", None)  # type: ignore[attr-defined]
    _execute_and_store_result.__doc__ = user_fn.__doc__  # type: ignore[attr-defined]
    _execute_and_store_result.__wrapped__ = user_fn  # type: ignore[attr-defined]

    return _execute_and_store_result
