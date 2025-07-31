# External Resources for FastMCP

A safe, controlled, and scalable approach to exposing external data to LLMs using MCP as a gateway protocol.

External Resources provides a way for MCP servers to declare and control access to external resources. Servers declare which external resources they provide access to as metadata containers. The validation middleware ensures tools only access declared resources, creating a secure gateway where LLMs interact with external data through MCP's controlled interface.

## Components

### ExternalResource

Represents a specific external resource with a fixed URI:

```python
from fastmcp.contrib.external_resources import ExternalResource

resource = ExternalResource(
    uri="s3://my-bucket/datasets/training-data.csv",
    name="Training Dataset",
    description="Customer behavior training data",
    mime_type="text/csv",
    meta={"size": "1.2GB", "updated": "2024-01-15"}
)
```

### ExternalResourceTemplate

Represents a pattern for accessing multiple related resources:

```python
from fastmcp.contrib.external_resources import ExternalResourceTemplate

template = ExternalResourceTemplate(
    uri_template="https://api.weather.com/v1/cities/{city}/forecast",
    name="Weather Forecast API",
    parameters=["city"],
    description="Get weather forecast for any city",
    mime_type="application/json"
)
```

### ValidationMiddleware

Ensures tools can only access declared external resources:

```python
from fastmcp.contrib.external_resources import ValidationMiddleware

app.add_middleware(ValidationMiddleware(app))
```

## Usage Example

```python
from fastmcp import FastMCP
from fastmcp.contrib.external_resources import (
    ExternalResource,
    ExternalResourceTemplate,
    register_external_resources,
    ValidationMiddleware
)

app = FastMCP("DataGateway")

# Declare external resources
resources = [
    ExternalResource(
        uri="s3://company-data/reports/2024/sales.pdf",
        name="2024 Sales Report",
        mime_type="application/pdf",
        meta={"confidential": True}
    ),
    ExternalResourceTemplate(
        uri_template="https://internal.api/v2/users/{user_id}",
        name="User API",
        parameters=["user_id"],
        mime_type="application/json"
    )
]

register_external_resources(app, resources)

# Optional: Enable validation
app.add_middleware(ValidationMiddleware(app))

# Tools can now safely work with these resources
@app.tool()
async def analyze_sales_report(report_uri: AnyUrl) -> str:
    # Tool implementation can fetch and process the external resource
    return f"Analyzing report at: {report_uri}"
```

