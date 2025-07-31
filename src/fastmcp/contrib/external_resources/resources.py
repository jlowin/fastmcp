"""External resource classes for URI validation middleware."""

from typing import Any

from fastmcp.resources import Resource
from fastmcp.resources.template import ResourceTemplate


class ExternalResource(Resource):
    """Represents an external resource that exists outside the MCP server.

    This is a metadata-only resource that describes an external resource
    without providing actual access to it. Used for URI validation to
    declare which external resources a server's tools are allowed to reference.
    """

    async def read(self) -> str:
        """Return a JSON representation of the resource metadata."""
        import json

        return json.dumps(
            {
                "uri": str(self.uri),
                "name": self.name,
                "description": self.description,
                "mime_type": self.mime_type,
                "meta": self.meta,
            },
            indent=2,
        )


class ExternalResourceTemplate(ResourceTemplate):
    """Represents a template for external resources with URI patterns.

    Similar to ExternalResource but supports URI templates with placeholders
    like 's3://bucket/{key}' or 'https://api.example.com/v1/{endpoint}'.
    """

    def __init__(
        self,
        uri_template: str,
        name: str,
        parameters: list[str],
        required: list[str] | None = None,
        **kwargs,
    ):
        """Initialize with automatic parameter schema generation from string list.

        Args:
            uri_template: URI template with placeholders
            name: Name of the resource template
            parameters: List of parameter names as strings
            required: List of required parameter names (defaults to all parameters)
            **kwargs: Additional fields like description, mime_type, _meta
        """
        # Default to all parameters being required if not specified
        if required is None:
            required = parameters

        # Generate JSON schema from parameter list
        parameters_schema = {
            "type": "object",
            "properties": {param: {"type": "string"} for param in parameters},
            "required": required,
        }

        super().__init__(
            uri_template=uri_template, name=name, parameters=parameters_schema, **kwargs
        )

    async def read(self, arguments: dict[str, Any]) -> str:
        """Return a JSON representation of the template with resolved arguments."""
        import json

        return json.dumps(
            {
                "uri_template": self.uri_template,
                "name": self.name,
                "description": self.description,
                "mime_type": self.mime_type,
                "meta": self.meta,
                "resolved_args": arguments,
            },
            indent=2,
        )


def register_external_resources(
    app, resources: list[ExternalResource | ExternalResourceTemplate]
):
    """Helper to register multiple external resources with a FastMCP app.

    Args:
        app: FastMCP application instance
        resources: List of ExternalResource or ExternalResourceTemplate instances
    """
    for resource in resources:
        if isinstance(resource, ExternalResource):
            app.add_resource(resource)
        elif isinstance(resource, ExternalResourceTemplate):
            app.add_template(resource)
