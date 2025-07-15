# FastMCP - Complete API Reference

**FastMCP** is a fast, Pythonic way to build MCP (Model Context Protocol) servers and clients. This document provides comprehensive API documentation for all components.

## Installation

```bash
pip install fastmcp
```

## Quick Start

```python
from fastmcp import FastMCP

server = FastMCP("My Server")

@server.tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b

@server.resource("config://settings")
def get_config() -> str:
    return "Configuration data"

server.run()
```

## Core Imports

```python
# Main classes
from fastmcp import FastMCP, Context, Client, settings

# Server components
from fastmcp.server import FastMCP, Context
from fastmcp.server.proxy import FastMCPProxy, ProxyClient
from fastmcp.server.openapi import FastMCPOpenAPI

# Client components
from fastmcp.client import (
    Client, WSTransport, SSETransport, StdioTransport,
    PythonStdioTransport, NodeStdioTransport, BearerAuth, OAuth
)

# Tools and resources
from fastmcp.tools import Tool, FunctionTool, ToolManager
from fastmcp.resources import Resource, ResourceTemplate, ResourceManager
from fastmcp.prompts import Prompt, PromptManager

# Utilities
from fastmcp.utilities.types import ImageContent, AudioContent, FileContent
from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool, mcp_resource, mcp_prompt
```


# Server API

## FastMCP Server Class

**Import:** `from fastmcp import FastMCP`

### Constructor
```python
FastMCP(
    name: str | None = None,
    instructions: str | None = None,
    version: str | None = None,
    auth: OAuthProvider | None = None,
    middleware: list[Middleware] | None = None,
    lifespan: Callable | None = None,
    tool_serializer: Callable[[Any], str] | None = None,
    cache_expiration_seconds: float | None = None,
    on_duplicate_tools: DuplicateBehavior | None = None,
    on_duplicate_resources: DuplicateBehavior | None = None,
    on_duplicate_prompts: DuplicateBehavior | None = None,
    resource_prefix_format: Literal["protocol", "path"] | None = None,
    mask_error_details: bool | None = None,
    tools: list[Tool | Callable] | None = None,
    dependencies: list[str] | None = None,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
)
```

### Core Methods
```python
# Running the server
async def run_async() -> None
def run() -> None
async def run_stdio_async(show_banner: bool = True) -> None
async def run_http_async() -> None
async def run_sse_async() -> None

# Component management
def add_tool(tool: Tool) -> Tool
def remove_tool(name: str) -> None
def add_resource(resource: Resource) -> Resource
def add_template(template: ResourceTemplate) -> ResourceTemplate
def add_prompt(prompt: Prompt) -> Prompt
def add_middleware(middleware: Middleware) -> None

# Server composition
def mount(path: str, server: FastMCP) -> None
def from_openapi(spec: dict | str | Path, **kwargs) -> FastMCPOpenAPI
def as_proxy(**kwargs) -> FastMCPProxy
```

### Decorators
```python
@server.tool(name=None, description=None, tags=None, output_schema=None)
def my_tool(param: str) -> str:
    return result

@server.resource(uri, name=None, description=None, mime_type=None)
def my_resource() -> str:
    return content

@server.prompt(name=None, description=None)
def my_prompt(param: str) -> str:
    return prompt_text

@server.custom_route(path, methods=["GET"])
def custom_endpoint():
    return response
```

## Context Class

**Import:** `from fastmcp import Context`

### Usage in Tools
```python
@server.tool
def my_tool(param: str, ctx: Context) -> str:
    ctx.info(f"Processing {param}")
    return result
```

### Methods
```python
# Logging
async def debug(message: str, logger_name: str | None = None)
async def info(message: str, logger_name: str | None = None)
async def warning(message: str, logger_name: str | None = None)
async def error(message: str, logger_name: str | None = None)

# Progress reporting
async def report_progress(progress: float, total: float | None = None, message: str | None = None)

# Resource access
async def read_resource(uri: str | AnyUrl) -> list[ReadResourceContents]

# Notifications
async def send_tool_list_changed()
async def send_resource_list_changed()
async def send_prompt_list_changed()

# Model interaction
async def sample() -> Any
async def elicit() -> Any

# Request context
def get_http_request() -> Request
```

### Properties
```python
ctx.client_id: str | None
ctx.request_id: str
ctx.session_id: str | None
ctx.session: ServerSession
ctx.request_context: RequestContext
```


# Client API

## Client Class

**Import:** `from fastmcp.client import Client`

### Constructor
```python
Client(
    transport: ClientTransport | FastMCP | AnyUrl | Path | MCPConfig | dict | str,
    roots: RootsList | RootsHandler | None = None,
    sampling_handler: SamplingHandler | None = None,
    log_handler: LogHandler | None = None,
    message_handler: MessageHandler | None = None,
    progress_handler: ProgressHandler | None = None,
    timeout: timedelta | float | int | None = None,
    init_timeout: timedelta | float | int | None = None,
)
```

### Connection Management
```python
async with client:
    # Use client
    pass

# Manual management
await client.__aenter__()
await client.__aexit__(None, None, None)
await client.close()
client.is_connected() -> bool
```

### Tool Operations
```python
# List available tools
tools = await client.list_tools()

# Call a tool
result = await client.call_tool(
    name="tool_name",
    arguments={"param": "value"},
    timeout=30.0,
    progress_handler=None,
    raise_on_error=True
)
```

### Resource Operations
```python
# List resources
resources = await client.list_resources()
templates = await client.list_resource_templates()

# Read a resource
content = await client.read_resource("file://path/to/resource")
```

### Prompt Operations
```python
# List prompts
prompts = await client.list_prompts()

# Get a prompt
result = await client.get_prompt(
    name="prompt_name",
    arguments={"param": "value"}
)
```

### Utility Methods
```python
# Test connection
is_alive = await client.ping()

# Cancel request
await client.cancel(request_id)

# Report progress
await client.progress(progress_token, progress=0.5, total=1.0)

# Set logging level
await client.set_logging_level("DEBUG")

# Notify roots changed
await client.send_roots_list_changed()
```

## Transport Classes

### HTTP Transports
```python
from fastmcp.client import WSTransport, SSETransport, StreamableHttpTransport

# WebSocket
transport = WSTransport("ws://localhost:8080/ws")

# Server-Sent Events
transport = SSETransport(
    "http://localhost:8080/sse",
    auth=BearerAuth("token"),
    headers={"Custom-Header": "value"}
)

# Streamable HTTP
transport = StreamableHttpTransport("http://localhost:8080/stream")
```

### Stdio Transports
```python
from fastmcp.client import (
    PythonStdioTransport, NodeStdioTransport,
    UvxStdioTransport, NpxStdioTransport
)

# Python script
transport = PythonStdioTransport(
    "server.py",
    args=["--verbose"],
    env={"DEBUG": "1"},
    python_executable="python3"
)

# Node.js script
transport = NodeStdioTransport(
    "server.js",
    args=["--port", "8080"],
    node_executable="node"
)

# uvx command
transport = UvxStdioTransport(
    "my-mcp-server",
    args=["--config", "config.json"]
)

# npx command
transport = NpxStdioTransport(
    "@my/mcp-server",
    args=["--verbose"]
)
```

### Special Transports
```python
from fastmcp.client import FastMCPTransport

# In-memory transport for FastMCP servers
transport = FastMCPTransport(server)
client = Client(transport)
```

## Authentication

### Bearer Token
```python
from fastmcp.client.auth import BearerAuth

auth = BearerAuth("your-token-here")
client = Client("http://localhost:8080", auth=auth)
```

### OAuth
```python
from fastmcp.client.auth import OAuth

auth = OAuth(
    mcp_url="http://localhost:8080/mcp/sse/",
    scopes=["read", "write"],
    client_name="My Client",
    token_storage_cache_dir=Path("~/.tokens")
)
client = Client("http://localhost:8080", auth=auth)
```


# Tools API

## Tool Decorator

**Import:** `from fastmcp import FastMCP`

### Basic Usage
```python
server = FastMCP()

@server.tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b

@server.tool(name="custom_name", description="Custom description")
def my_tool(param: str) -> str:
    return f"Result: {param}"

@server.tool(tags={"math", "utility"})
def calculate(expression: str) -> float:
    """Calculate mathematical expression"""
    return eval(expression)
```

### Advanced Tool Options
```python
@server.tool(
    name="advanced_tool",
    description="An advanced tool with custom schema",
    output_schema={
        "type": "object",
        "properties": {
            "result": {"type": "string"},
            "metadata": {"type": "object"}
        }
    },
    exclude_args=["internal_param"],
    enabled=True
)
def advanced_tool(data: str, internal_param: str = "hidden") -> dict:
    return {
        "result": f"Processed: {data}",
        "metadata": {"processed_at": "2024-01-01"}
    }
```

### Using Context in Tools
```python
from fastmcp import Context

@server.tool
def tool_with_context(message: str, ctx: Context) -> str:
    """Tool that uses context for logging and progress"""
    ctx.info(f"Processing message: {message}")
    ctx.report_progress(0.5, message="Halfway done")
    return f"Processed: {message}"
```

## Tool Classes

### Tool Base Class
```python
from fastmcp.tools import Tool, ToolResult

class CustomTool(Tool):
    def __init__(self, name: str, description: str):
        super().__init__(name=name, description=description)
    
    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        # Custom tool logic
        return ToolResult(content="Result")

# Add to server
tool = CustomTool("my_tool", "Custom tool")
server.add_tool(tool)
```

### FunctionTool
```python
from fastmcp.tools import FunctionTool

def my_function(x: int) -> str:
    return str(x)

tool = FunctionTool.from_function(
    my_function,
    name="convert_to_string",
    description="Convert integer to string"
)
server.add_tool(tool)
```

### ToolResult
```python
from fastmcp.tools import ToolResult

# Simple text result
result = ToolResult(content="Simple text result")

# Structured result
result = ToolResult(
    content="Display text",
    structured_content={"data": "value", "count": 42}
)

# Multiple content blocks
result = ToolResult(content=[
    {"type": "text", "text": "First part"},
    {"type": "text", "text": "Second part"}
])
```

## Tool Transformations

### ArgTransform
```python
from fastmcp.tools.tool_transform import ArgTransform, TransformedTool

# Original tool
@server.tool
def original_tool(name: str, age: int, debug: bool = False) -> str:
    return f"{name} is {age} years old"

# Transform arguments
transformed = TransformedTool.from_tool(
    original_tool,
    name="simplified_tool",
    transform_args={
        "name": ArgTransform(description="Person's full name"),
        "age": ArgTransform(default=25),
        "debug": ArgTransform(hide=True, default=False)
    }
)
server.add_tool(transformed)
```

### Forward Functions
```python
from fastmcp.tools.tool_transform import forward, forward_raw

@server.tool
def wrapper_tool(simplified_param: str) -> str:
    # Transform and forward to parent tool
    return await forward(
        original_param=simplified_param.upper(),
        hidden_param="constant"
    )

@server.tool
def direct_wrapper(param: str) -> str:
    # Forward directly without transformation
    return await forward_raw(param=param)
```


# Resources API

## Resource Decorator

### Basic Usage
```python
server = FastMCP()

@server.resource("file://config.json")
def get_config() -> str:
    """Get application configuration"""
    return json.dumps({"setting": "value"})

@server.resource("data://users.csv", mime_type="text/csv")
def get_users() -> str:
    return "name,email\nJohn,john@example.com"
```

### Template Resources
```python
@server.resource("user://{user_id}/profile")
def get_user_profile(user_id: str) -> dict:
    """Get user profile by ID"""
    return {
        "user_id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com"
    }

@server.resource("weather://{city}/current")
def get_weather(city: str) -> str:
    """Get current weather for a city"""
    return f"Weather in {city}: Sunny, 25°C"
```

## Resource Classes

### Built-in Resource Types
```python
from fastmcp.resources import (
    TextResource, BinaryResource, FileResource,
    HttpResource, DirectoryResource
)

# Text resource
text_res = TextResource(
    uri="data://sample.txt",
    text="Sample content",
    name="Sample Text"
)

# Binary resource
binary_res = BinaryResource(
    uri="data://image.png",
    data=b"\x89PNG...",
    mime_type="image/png"
)

# File resource
file_res = FileResource(
    uri="file://document.pdf",
    path=Path("./document.pdf"),
    is_binary=True
)

# HTTP resource
http_res = HttpResource(
    uri="api://users",
    url="https://api.example.com/users",
    mime_type="application/json"
)

# Directory resource
dir_res = DirectoryResource(
    uri="files://project/",
    path=Path("./project"),
    recursive=True,
    pattern="*.py"
)

# Add to server
for resource in [text_res, binary_res, file_res, http_res, dir_res]:
    server.add_resource(resource)
```

### Custom Resource Class
```python
from fastmcp.resources import Resource

class DatabaseResource(Resource):
    def __init__(self, uri: str, query: str):
        super().__init__(uri=uri, mime_type="application/json")
        self.query = query
    
    async def read(self) -> str:
        # Execute database query
        result = await db.execute(self.query)
        return json.dumps(result)

# Usage
db_resource = DatabaseResource(
    uri="db://users",
    query="SELECT * FROM users"
)
server.add_resource(db_resource)
```

### Resource Templates
```python
from fastmcp.resources import ResourceTemplate

class UserResourceTemplate(ResourceTemplate):
    def __init__(self):
        super().__init__(
            uri_template="user://{user_id}/data",
            name="User Data Template",
            description="Access user data by ID"
        )
    
    async def read(self, arguments: dict[str, Any]) -> str:
        user_id = arguments["user_id"]
        # Fetch user data
        return json.dumps({"user_id": user_id, "data": "..."})

template = UserResourceTemplate()
server.add_template(template)
```

# Prompts API

## Prompt Decorator

### Basic Usage
```python
server = FastMCP()

@server.prompt
def helpful_assistant(task: str) -> str:
    """Create a helpful assistant prompt"""
    return f"You are a helpful assistant. Please help with: {task}"

@server.prompt(name="code_reviewer")
def review_code(code: str, language: str = "python") -> str:
    """Generate code review prompt"""
    return f"Review this {language} code:\n\n{code}\n\nProvide feedback."
```

### Structured Prompts
```python
from fastmcp.prompts import Message

@server.prompt
def conversation_starter(topic: str) -> list:
    """Create a conversation starter"""
    return [
        Message("You are an expert conversationalist.", role="system"),
        Message(f"Start a conversation about {topic}", role="user")
    ]

@server.prompt
def multi_turn_prompt(context: str, question: str) -> list:
    """Create multi-turn conversation prompt"""
    return [
        Message("You are a knowledgeable assistant.", role="system"),
        Message(f"Context: {context}", role="user"),
        Message("I understand the context.", role="assistant"),
        Message(f"Question: {question}", role="user")
    ]
```

## Prompt Classes

### Custom Prompt Class
```python
from fastmcp.prompts import Prompt, PromptArgument

class CustomPrompt(Prompt):
    def __init__(self, name: str):
        super().__init__(
            name=name,
            description="Custom prompt",
            arguments=[
                PromptArgument(name="input", description="Input text", required=True),
                PromptArgument(name="style", description="Response style", required=False)
            ]
        )
    
    async def render(self, arguments: dict[str, Any]) -> list:
        input_text = arguments["input"]
        style = arguments.get("style", "professional")
        
        return [
            Message(f"Respond in a {style} style.", role="system"),
            Message(input_text, role="user")
        ]

prompt = CustomPrompt("custom_prompt")
server.add_prompt(prompt)
```


# Advanced Features

## Server Composition

### Mounting Servers
```python
# Create sub-servers
auth_server = FastMCP("Auth Service")
data_server = FastMCP("Data Service")

@auth_server.tool
def login(username: str, password: str) -> str:
    return "auth_token"

@data_server.tool
def get_data(token: str) -> dict:
    return {"data": "value"}

# Mount on main server
main_server = FastMCP("Main Server")
main_server.mount("/auth", auth_server)
main_server.mount("/data", data_server)
```

### Proxy Servers
```python
from fastmcp.server.proxy import FastMCPProxy
from fastmcp.client import Client

def client_factory():
    return Client("http://remote-server:8080")

proxy = FastMCPProxy(client_factory=client_factory)
proxy.run()
```

### OpenAPI Integration
```python
from fastmcp.server.openapi import FastMCPOpenAPI

# From OpenAPI spec
server = FastMCPOpenAPI.from_openapi("openapi.json")

# Or from URL
server = FastMCPOpenAPI.from_openapi("https://api.example.com/openapi.json")
```

## Middleware

### Built-in Middleware
```python
from fastmcp.server.middleware import (
    LoggingMiddleware, TimingMiddleware, 
    RateLimitingMiddleware, ErrorHandlingMiddleware
)

server = FastMCP(
    "My Server",
    middleware=[
        LoggingMiddleware(),
        TimingMiddleware(),
        RateLimitingMiddleware(max_requests=100, window_seconds=60),
        ErrorHandlingMiddleware()
    ]
)
```

### Custom Middleware
```python
from fastmcp.server.middleware import Middleware

class CustomMiddleware(Middleware):
    async def __call__(self, request, call_next):
        # Pre-processing
        print(f"Request: {request.method}")
        
        # Call next middleware/handler
        response = await call_next(request)
        
        # Post-processing
        print(f"Response: {response.status_code}")
        return response

server.add_middleware(CustomMiddleware())
```

## Authentication

### OAuth Provider
```python
from fastmcp.server.auth import OAuthProvider

auth_provider = OAuthProvider(
    client_id="your-client-id",
    client_secret="your-client-secret",
    authorization_url="https://auth.example.com/oauth/authorize",
    token_url="https://auth.example.com/oauth/token",
    scopes=["read", "write"]
)

server = FastMCP("Secure Server", auth=auth_provider)
```

### Bearer Token Auth
```python
from fastmcp.server.auth.providers import BearerAuthProvider

def validate_token(token: str) -> dict | None:
    # Validate token and return user info
    if token == "valid-token":
        return {"user_id": "123", "scopes": ["read", "write"]}
    return None

auth_provider = BearerAuthProvider(validate_token)
server = FastMCP("Secure Server", auth=auth_provider)
```

## Content Types

### Rich Content
```python
from fastmcp.utilities.types import ImageContent, AudioContent, FileContent

@server.tool
def generate_image(prompt: str) -> ImageContent:
    """Generate an image from text prompt"""
    image_data = generate_image_bytes(prompt)
    return ImageContent(data=image_data, mime_type="image/png")

@server.tool
def process_audio(audio_file: str) -> AudioContent:
    """Process audio file"""
    audio_data = process_audio_file(audio_file)
    return AudioContent(data=audio_data, mime_type="audio/wav")

@server.resource("document://report.pdf")
def get_report() -> FileContent:
    """Get PDF report"""
    return FileContent(
        path="./report.pdf",
        mime_type="application/pdf"
    )
```

# CLI Usage

## Development
```bash
# Run with MCP Inspector for development
fastmcp dev server.py --with-editable . --ui-port 3000

# Run specific server object
fastmcp dev server.py:app --with requests pandas
```

## Production
```bash
# Run with stdio transport
fastmcp run server.py

# Run with HTTP transport
fastmcp run server.py --transport http --port 8080

# Run with specific host and path
fastmcp run server.py --transport http --host 0.0.0.0 --port 8080 --path /mcp
```

## Installation
```bash
# Install for Claude Desktop
fastmcp install claude-desktop server.py

# Install for Claude for VS Code
fastmcp install claude-code server.py

# Install for Cursor
fastmcp install cursor server.py

# Generate MCP config JSON
fastmcp install mcp-json server.py > config.json
```

## Inspection
```bash
# Inspect server capabilities
fastmcp inspect server.py -o server-info.json

# Inspect specific server object
fastmcp inspect server.py:app
```


# Contrib Components

## MCP Mixin

**Import:** `from fastmcp.contrib.mcp_mixin import MCPMixin, mcp_tool, mcp_resource, mcp_prompt`

### Usage Pattern
```python
class MyService(MCPMixin):
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    @mcp_tool(name="fetch_data", description="Fetch data from API")
    def fetch_data(self, endpoint: str) -> dict:
        # Use self.api_key to make API call
        return {"data": f"Data from {endpoint}"}
    
    @mcp_resource("config://service")
    def get_config(self) -> str:
        return json.dumps({"api_key": "***", "status": "active"})
    
    @mcp_prompt(name="api_helper")
    def api_helper_prompt(self, task: str) -> str:
        return f"Help with API task: {task}"
    
    def register_with_mcp(self, server: FastMCP):
        super().register_with_mcp(server)
        # Additional registration logic

# Usage
service = MyService("your-api-key")
service.register_with_mcp(server)
```

## Bulk Tool Caller

**Import:** `from fastmcp.contrib.bulk_tool_caller import BulkToolCaller`

### Setup
```python
bulk_caller = BulkToolCaller()
bulk_caller.register_with_mcp(server)
```

### Usage
```python
# Client can now call multiple tools in one request
result = await client.call_tool("bulk_call_tools", {
    "requests": [
        {"name": "tool1", "arguments": {"param": "value1"}},
        {"name": "tool2", "arguments": {"param": "value2"}},
        {"name": "tool3", "arguments": {"param": "value3"}}
    ]
})
```

## Component Manager

**Import:** `from fastmcp.contrib.component_manager import set_up_component_manager`

### Setup
```python
# Add component management endpoints
set_up_component_manager(
    server,
    path="/admin/",
    required_scopes=["admin"]
)
```

### Features
- List all tools, resources, and prompts
- Enable/disable components dynamically
- Get component statistics
- Component health checks

# Configuration

## Settings

**Import:** `from fastmcp import settings`

### Environment Variables
```bash
# Logging
FASTMCP_LOG_LEVEL=DEBUG
FASTMCP_ENABLE_RICH_TRACEBACKS=true

# Server behavior
FASTMCP_MASK_ERROR_DETAILS=false
FASTMCP_RESOURCE_PREFIX_FORMAT=path

# Client behavior
FASTMCP_CLIENT_INIT_TIMEOUT=30
FASTMCP_CLIENT_RAISE_FIRST_EXCEPTIONGROUP_ERROR=true

# Component filtering
FASTMCP_INCLUDE_TAGS=production,stable
FASTMCP_EXCLUDE_TAGS=debug,experimental
```

### Programmatic Configuration
```python
from fastmcp.settings import Settings

# Access current settings
print(settings.log_level)
print(settings.home)  # ~/.fastmcp

# Create custom settings
custom_settings = Settings(
    log_level="DEBUG",
    mask_error_details=True,
    include_tags={"production"},
    exclude_tags={"debug"}
)
```

# Utilities

## Logging
```python
from fastmcp.utilities.logging import get_logger, configure_logging

# Configure logging
configure_logging("DEBUG", enable_rich=True)

# Get logger
logger = get_logger("my_component")
logger.info("Component initialized")
```

## Inspection
```python
from fastmcp.utilities.inspect import inspect_fastmcp

# Inspect server programmatically
info = await inspect_fastmcp(server)
print(f"Server: {info.name}")
print(f"Tools: {len(info.tools)}")
print(f"Resources: {len(info.resources)}")
```

## Type Utilities
```python
from fastmcp.utilities.types import (
    get_cached_typeadapter,
    issubclass_safe,
    find_kwarg_by_type
)

# Type adapter caching
adapter = get_cached_typeadapter(MyModel)

# Safe subclass checking
if issubclass_safe(MyClass, BaseClass):
    print("MyClass is a subclass of BaseClass")

# Find function parameter by type
ctx_param = find_kwarg_by_type(my_function, Context)
```

# Error Handling

## Tool Errors
```python
from fastmcp.exceptions import ToolError, ResourceError

@server.tool
def risky_tool(param: str) -> str:
    if not param:
        raise ToolError("Parameter cannot be empty")
    
    try:
        result = dangerous_operation(param)
        return result
    except Exception as e:
        raise ToolError(f"Operation failed: {str(e)}") from e
```

## Resource Errors
```python
@server.resource("data://sensitive")
def get_sensitive_data() -> str:
    if not user_has_permission():
        raise ResourceError("Access denied", status_code=403)
    
    try:
        return load_sensitive_data()
    except FileNotFoundError:
        raise ResourceError("Data not found", status_code=404)
```

## Global Error Handling
```python
from fastmcp.server.middleware import ErrorHandlingMiddleware

# Custom error handler
def custom_error_handler(error: Exception) -> dict:
    if isinstance(error, ValueError):
        return {"error": "Invalid input", "code": "INVALID_INPUT"}
    return {"error": "Internal error", "code": "INTERNAL_ERROR"}

middleware = ErrorHandlingMiddleware(error_handler=custom_error_handler)
server.add_middleware(middleware)
```

# Testing

## Testing Tools
```python
import pytest
from fastmcp.utilities.tests import create_test_client

@pytest.fixture
def client():
    server = FastMCP("Test Server")
    
    @server.tool
    def test_tool(x: int) -> int:
        return x * 2
    
    return create_test_client(server)

@pytest.mark.asyncio
async def test_tool_call(client):
    result = await client.call_tool("test_tool", {"x": 5})
    assert result.content == "10"
```

## Testing Resources
```python
@pytest.mark.asyncio
async def test_resource_read(client):
    resources = await client.list_resources()
    assert len(resources) > 0
    
    content = await client.read_resource("test://resource")
    assert "expected content" in content
```

# Best Practices

## Tool Design
- Use clear, descriptive names and docstrings
- Validate input parameters
- Return structured data when possible
- Use Context for logging and progress reporting
- Handle errors gracefully

## Resource Organization
- Use consistent URI schemes
- Group related resources under common prefixes
- Implement templates for parameterized resources
- Cache expensive resource operations

## Server Architecture
- Use middleware for cross-cutting concerns
- Mount sub-servers for logical separation
- Implement proper authentication and authorization
- Monitor performance and resource usage

## Client Usage
- Use connection pooling for multiple requests
- Implement proper error handling and retries
- Use appropriate timeouts
- Handle authentication token refresh

---

*This documentation covers FastMCP v2. For the latest updates, visit [gofastmcp.com](https://gofastmcp.com)*
