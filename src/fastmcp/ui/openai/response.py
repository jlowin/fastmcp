"""Response transformation utilities for OpenAI widgets."""

from __future__ import annotations

from typing import Any

WidgetToolResponse = dict[str, Any]


def build_widget_tool_response(
    response_text: str | None = None,
    structured_content: dict[str, Any] | None = None,
) -> WidgetToolResponse:
    """Build a standardized OpenAI widget tool response.

    This helper is available for advanced use cases, but the widget decorator
    automatically transforms simple return values (str, dict, tuple) so you
    typically don't need to call this directly.

    Args:
        response_text: Narrative text shown in the conversation
        structured_content: Data passed to the widget JavaScript component

    Returns:
        Formatted response dict with content and structuredContent

    Examples:
        Build a response with both text and data:
        ```python
        return build_widget_tool_response(
            response_text="Showing weather for Seattle",
            structured_content={"city": "Seattle", "temp": 72}
        )
        ```

        Data only (no narrative):
        ```python
        return build_widget_tool_response(
            structured_content={"data": [1, 2, 3]}
        )
        ```
    """
    content = (
        [
            {
                "type": "text",
                "text": response_text,
            }
        ]
        if response_text
        else []
    )

    return {"content": content, "structuredContent": structured_content or {}}


def transform_widget_response(result: Any) -> WidgetToolResponse:
    """Auto-transform widget function return value to OpenAI format.

    Supports three return patterns:
    - str: Narrative text only
    - dict: Structured data for widget (no narrative)
    - tuple[str, dict]: Both narrative and data

    Args:
        result: The widget function's return value

    Returns:
        Formatted response dict with content and structuredContent

    Raises:
        TypeError: If return type is not str, dict, or tuple[str, dict]

    Examples:
        Transform a string:
        ```python
        result = transform_widget_response("Showing map")
        # {"content": [{"type": "text", "text": "Showing map"}], "structuredContent": {}}
        ```

        Transform a dict:
        ```python
        result = transform_widget_response({"lat": 47.6, "lon": -122.3})
        # {"content": [], "structuredContent": {"lat": 47.6, "lon": -122.3}}
        ```

        Transform a tuple:
        ```python
        result = transform_widget_response(("Showing map", {"lat": 47.6}))
        # {"content": [{"type": "text", "text": "Showing map"}], "structuredContent": {"lat": 47.6}}
        ```
    """
    if isinstance(result, str):
        return build_widget_tool_response(
            response_text=result if result else None,
            structured_content=None,
        )
    elif isinstance(result, dict):
        return build_widget_tool_response(
            response_text=None,
            structured_content=result,
        )
    elif isinstance(result, tuple):
        if len(result) != 2:
            raise TypeError(
                f"Widget function returned tuple of length {len(result)}, expected 2 (text, data). "
                f"Return either: str (text only), dict (data only), or tuple[str, dict] (both)"
            )

        text, data = result

        if text is not None and not isinstance(text, str):
            raise TypeError(
                f"First element of tuple must be str or None, got {type(text).__name__}. "
                f"Return format: tuple[str | None, dict[str, Any]]"
            )

        if data is not None and not isinstance(data, dict):
            raise TypeError(
                f"Second element of tuple must be dict or None, got {type(data).__name__}. "
                f"Return format: tuple[str | None, dict[str, Any]]"
            )

        return build_widget_tool_response(
            response_text=text,
            structured_content=data,
        )
    else:
        raise TypeError(
            f"Widget function must return str, dict, or tuple[str, dict], got {type(result).__name__}. "
            f"Examples:\n"
            f"  - return 'Showing map'  # Text only\n"
            f"  - return {{'lat': 47.6}}  # Data only\n"
            f"  - return ('Showing map', {{'lat': 47.6}})  # Both"
        )
