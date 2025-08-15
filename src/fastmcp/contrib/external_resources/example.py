"""Example demonstrating external resources with MCP as a gateway protocol."""

from pydantic import AnyUrl

from fastmcp import FastMCP
from fastmcp.contrib.external_resources import (
    ExternalResource,
    ExternalResourceTemplate,
    ValidationMiddleware,
    register_external_resources,
)

# Create server with external resource gateway
app = FastMCP("External Resources Gateway")

# Optional: Add validation middleware for access control
app.add_middleware(ValidationMiddleware(app))

# Define external resources as metadata containers
external_resources = [
    ExternalResource(
        uri=AnyUrl("s3://my-bucket/data/training.csv"),
        name="Training Data",
        description="ML training dataset stored in S3",
        mime_type="text/csv",
        meta={"size": "1.2GB", "updated": "2024-01-15"},
    ),
    ExternalResource(
        uri=AnyUrl("https://api.company.com/v1/users"),
        name="Users API",
        description="Company users API endpoint",
        mime_type="application/json",
    ),
    ExternalResourceTemplate(
        uri_template="file:///config/{env}",
        name="Config Files",
        parameters=["env"],
        description="Environment-specific configuration files",
        mime_type="application/json",
    ),
    ExternalResourceTemplate(
        uri_template="s3://my-bucket/models/{model_name}",
        name="ML Models",
        parameters=["model_name"],
        description="Trained ML models in S3",
        meta={"format": "pytorch"},
    ),
    ExternalResourceTemplate(
        uri_template="https://api.example.com/data/{dataset}/{version}",
        name="Versioned Datasets",
        parameters=["dataset", "version"],
        required=["dataset"],  # version is optional
        description="Versioned datasets with optional version parameter",
    ),
]

# Register all external resources
register_external_resources(app, external_resources)


# Tool without annotation - validated by default
@app.tool()
async def process_data(data_uri: AnyUrl) -> str:
    """Process data from a URI."""
    return f"Processing data from: {data_uri}"


# Tool with explicit opt-out - not validated
@app.tool(annotations={"openWorldHint": True})
async def download_anything(url: AnyUrl) -> str:
    """Download from any URL."""
    return f"Downloading from: {url}"
