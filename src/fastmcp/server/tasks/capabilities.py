"""SEP-1686 task capabilities declaration."""

from mcp.types import (
    ServerTasksCapability,
    ServerTasksRequestsCapability,
    TasksCallCapability,
    TasksCancelCapability,
    TasksListCapability,
    TasksToolsCapability,
)


def get_task_capabilities() -> ServerTasksCapability:
    """Return the SEP-1686 task capabilities.

    Returns task capabilities as a first-class ServerCapabilities field,
    declaring support for list, cancel, and request operations per SEP-1686.

    Note: prompts/resources are passed via extra_data since the SDK types
    don't include them yet (FastMCP supports them ahead of the spec).
    """
    return ServerTasksCapability(
        list=TasksListCapability(),
        cancel=TasksCancelCapability(),
        requests=ServerTasksRequestsCapability(
            tools=TasksToolsCapability(call=TasksCallCapability()),
            prompts={"get": {}},  # type: ignore[call-arg]  # extra_data for forward compat
            resources={"read": {}},  # type: ignore[call-arg]  # extra_data for forward compat
        ),
    )
