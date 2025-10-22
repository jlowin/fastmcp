"""OpenAI-specific metadata builders for widgets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# Default CSP resource domains for OpenAI widgets
DEFAULT_CSP_RESOURCES: tuple[str, ...] = ("https://persistent.oaistatic.com",)

# Default resource annotations for widget HTML
DEFAULT_RESOURCE_ANNOTATIONS: dict[str, Any] = {
    "readOnlyHint": True,
    "idempotentHint": True,
}

# Default tool annotations for widget tools
DEFAULT_TOOL_ANNOTATIONS: dict[str, Any] = {
    "destructiveHint": False,
    "openWorldHint": False,
    "readOnlyHint": True,
}


def _normalize_sequence(
    seq: Sequence[str] | None, default: Sequence[str]
) -> list[str]:
    """Normalize a sequence to a list, using default if None."""
    return list(seq if seq is not None else default)


def build_widget_resource_meta(
    *,
    title: str,
    widget_description: str | None = None,
    widget_prefers_border: bool = True,
    widget_csp_resources: Sequence[str] | None = None,
    widget_csp_connect: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build _meta dict for widget HTML resource.

    Args:
        title: Widget title
        widget_description: Description of widget UI (defaults to "{title} widget UI.")
        widget_prefers_border: Whether widget prefers a border
        widget_csp_resources: CSP resource_domains list
        widget_csp_connect: CSP connect_domains list

    Returns:
        Metadata dict with OpenAI widget configuration

    Examples:
        Build basic widget metadata:
        ```python
        meta = build_widget_resource_meta(title="Pizza Map")
        # {
        #   "openai/widgetDescription": "Pizza Map widget UI.",
        #   "openai/widgetPrefersBorder": True,
        #   "openai/widgetCSP": {...}
        # }
        ```
    """
    return {
        "openai/widgetDescription": widget_description or f"{title} widget UI.",
        "openai/widgetPrefersBorder": widget_prefers_border,
        "openai/widgetCSP": {
            "resource_domains": _normalize_sequence(
                widget_csp_resources, DEFAULT_CSP_RESOURCES
            ),
            "connect_domains": _normalize_sequence(widget_csp_connect, ()),
        },
    }


def build_embedded_widget_resource(
    *,
    template_uri: str,
    html: str,
    title: str,
    mime_type: str = "text/html+skybridge",
    widget_description: str | None = None,
    widget_prefers_border: bool = True,
    widget_csp_resources: Sequence[str] | None = None,
    widget_csp_connect: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build embedded widget resource structure for tool metadata.

    This creates the openai.com/widget embedded resource that ChatGPT
    uses to render the widget.

    Args:
        template_uri: Widget template URI (e.g. "ui://widget/pizza-map.html")
        html: Widget HTML content
        title: Widget title
        mime_type: MIME type for the widget HTML
        widget_description: Description of widget UI (defaults to "{title} widget UI.")
        widget_prefers_border: Whether widget prefers a border
        widget_csp_resources: CSP resource_domains list
        widget_csp_connect: CSP connect_domains list

    Returns:
        Embedded resource structure for tool metadata

    Examples:
        Build embedded resource:
        ```python
        resource = build_embedded_widget_resource(
            template_uri="ui://widget/map.html",
            html="<div>...</div>",
            title="Map Widget"
        )
        ```
    """
    return {
        "type": "resource",
        "resource": {
            "type": "text",
            "uri": template_uri,
            "mimeType": mime_type,
            "text": html,
            "title": title,
            "_meta": build_widget_resource_meta(
                title=title,
                widget_description=widget_description,
                widget_prefers_border=widget_prefers_border,
                widget_csp_resources=widget_csp_resources,
                widget_csp_connect=widget_csp_connect,
            ),
        },
    }


def build_widget_tool_meta(
    *,
    template_uri: str,
    html: str,
    title: str,
    invoking: str | None = None,
    invoked: str | None = None,
    mime_type: str = "text/html+skybridge",
    widget_description: str | None = None,
    widget_prefers_border: bool = True,
    widget_csp_resources: Sequence[str] | None = None,
    widget_csp_connect: Sequence[str] | None = None,
    widget_accessible: bool = True,
    result_can_produce_widget: bool = True,
    additional_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build _meta dict for widget tool.

    Args:
        template_uri: Widget template URI (e.g. "ui://widget/pizza-map.html")
        html: Widget HTML content
        title: Widget title
        invoking: Status message shown while tool is executing
        invoked: Status message shown after tool completes
        mime_type: MIME type for the widget HTML
        widget_description: Description of widget UI (defaults to "{title} widget UI.")
        widget_prefers_border: Whether widget prefers a border
        widget_csp_resources: CSP resource_domains list
        widget_csp_connect: CSP connect_domains list
        widget_accessible: Whether widget is accessible
        result_can_produce_widget: Whether result can produce a widget
        additional_meta: Additional metadata to merge

    Returns:
        Metadata dict with OpenAI widget tool configuration

    Examples:
        Build widget tool metadata:
        ```python
        meta = build_widget_tool_meta(
            template_uri="ui://widget/map.html",
            html="<div>...</div>",
            title="Map Widget",
            invoking="Loading map...",
            invoked="Map loaded!"
        )
        ```
    """
    meta: dict[str, Any] = {
        "openai.com/widget": build_embedded_widget_resource(
            template_uri=template_uri,
            html=html,
            title=title,
            mime_type=mime_type,
            widget_description=widget_description,
            widget_prefers_border=widget_prefers_border,
            widget_csp_resources=widget_csp_resources,
            widget_csp_connect=widget_csp_connect,
        ),
        "openai/outputTemplate": template_uri,
        "openai/widgetAccessible": widget_accessible,
        "openai/resultCanProduceWidget": result_can_produce_widget,
    }

    # Add invocation status messages if provided
    if invoking is not None:
        meta["openai/toolInvocation/invoking"] = invoking
    if invoked is not None:
        meta["openai/toolInvocation/invoked"] = invoked

    # Merge additional metadata
    if additional_meta:
        meta.update(additional_meta)

    return meta


def merge_tool_annotations(
    user_annotations: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge user annotations with default widget tool annotations.

    Args:
        user_annotations: User-provided annotations to merge

    Returns:
        Combined annotations dict with defaults and user overrides

    Examples:
        Merge annotations:
        ```python
        annotations = merge_tool_annotations({"customHint": True})
        # {
        #   "destructiveHint": False,
        #   "openWorldHint": False,
        #   "readOnlyHint": True,
        #   "customHint": True
        # }
        ```
    """
    combined = dict(DEFAULT_TOOL_ANNOTATIONS)
    if user_annotations:
        combined.update(user_annotations)
    return combined


def merge_resource_annotations(
    user_annotations: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge user annotations with default widget resource annotations.

    Args:
        user_annotations: User-provided annotations to merge

    Returns:
        Combined annotations dict with defaults and user overrides

    Examples:
        Merge annotations:
        ```python
        annotations = merge_resource_annotations({"customHint": True})
        # {
        #   "readOnlyHint": True,
        #   "idempotentHint": True,
        #   "customHint": True
        # }
        ```
    """
    combined = dict(DEFAULT_RESOURCE_ANNOTATIONS)
    if user_annotations:
        combined.update(user_annotations)
    return combined
