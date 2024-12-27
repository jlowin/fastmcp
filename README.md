<!-- omit in toc -->
# FastMCP 🚀

<div align="center">

<strong>The fast, Pythonic way to build MCP servers.</strong>

[![PyPI - Version](https://img.shields.io/pypi/v/fastmcp.svg)](https://pypi.org/project/fastmcp)
[![Tests](https://github.com/jlowin/fastmcp/actions/workflows/run-tests.yml/badge.svg)](https://github.com/jlowin/fastmcp/actions/workflows/run-tests.yml)
[![License](https://img.shields.io/github/license/jlowin/fastmcp.svg)](https://github.com/jlowin/fastmcp/blob/main/LICENSE)


</div>

[Model Context Protocol (MCP)](https://modelcontextprotocol.io) servers are a new, standardized way to provide context and tools to your LLMs, and FastMCP makes building MCP servers simple and intuitive. Create tools, expose resources, and define prompts with clean, Pythonic code:

```python
# demo.py

from fastmcp import FastMCP


mcp = FastMCP("Demo 🚀")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b
```

That's it! Give Claude access to the server by running:

```bash
fastmcp install demo.py
```

FastMCP handles all the complex protocol details and server management, so you can focus on building great tools. It's designed to be high-level and Pythonic - in most cases, decorating a function is all you need.

> [!NOTE]
> For a TypeScript implementation, see [FastMCP](https://github.com/punkpeye/fastmcp).

### Key features:
* **Fast**: High-level interface means less code and faster development
* **Simple**: Build MCP servers with minimal boilerplate
* **Pythonic**: Feels natural to Python developers
* **Complete***: FastMCP aims to provide a full implementation of the core MCP specification

(\*emphasis on *aims*)

🚨 🚧 🏗️ *FastMCP is under active development, as is the MCP specification itself. Core features are working but some advanced capabilities are still in progress.* 


<!-- omit in toc -->
## Table of Contents

- [Installation](#installation)
- [Quickstart](#quickstart)
- [What is MCP?](#what-is-mcp)
- [Core Concepts](#core-concepts)
  - [Server](#server)
  - [Resources](#resources)
  - [Tools](#tools)
  - [Prompts](#prompts)
  - [Images](#images)
  - [Context](#context)
- [Running Your Server](#running-your-server)
  - [Development Mode (Recommended for Building \& Testing)](#development-mode-recommended-for-building--testing)
  - [Claude Desktop Integration (For Regular Use)](#claude-desktop-integration-for-regular-use)
  - [Direct Execution (For Advanced Use Cases)](#direct-execution-for-advanced-use-cases)
  - [Server Object Names](#server-object-names)
- [Examples](#examples)
  - [Echo Server](#echo-server)
  - [SQLite Explorer](#sqlite-explorer)
- [Contributing](#contributing)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation-1)
  - [Testing](#testing)
  - [Formatting](#formatting)
  - [Opening a Pull Request](#opening-a-pull-request)

## Installation

We strongly recommend installing FastMCP with [uv](https://docs.astral.sh/uv/), as it is required for deploying servers:

```bash
uv pip install fastmcp
```

Note: on macOS, uv may need to be installed with Homebrew (`brew install uv`) in order to make it available to the Claude Desktop app.

Alternatively, to use the SDK without deploying, you may use pip:

```bash
pip install fastmcp
```

## Quickstart

Let's create a simple MCP server that exposes a calculator tool and some data:

```python
# server.py

from fastmcp import FastMCP


# Create an MCP server
mcp = FastMCP("Demo")


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"
```

You can install this server in [Claude Desktop](https://claude.ai/download) and interact with it right away by running:
```bash
fastmcp install server.py
```

Alternatively, you can test it with the MCP Inspector:
```bash
fastmcp dev server.py
```

![MCP Inspector](/docs/assets/demo-inspector.png)

## What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io) lets you build servers that expose data and functionality to LLM applications in a secure, standardized way. Think of it like a web API, but specifically designed for LLM interactions. MCP servers can:

- Expose data through **Resources** (think of these sort of like GET endpoints; they are used to load information into the LLM's context)
- Provide functionality through **Tools** (sort of like POST endpoints; they are used to execute code or otherwise produce a side effect)
- Define interaction patterns through **Prompts** (reusable templates for LLM interactions)
- And more!

There is a low-level [Python SDK](https://github.com/modelcontextprotocol/python-sdk) available for implementing the protocol directly, but FastMCP aims to make that easier by providing a high-level, Pythonic interface.

## Core Concepts


### Server

The FastMCP server is your core interface to the MCP protocol. It handles connection management, protocol compliance, and message routing:

```python
from fastmcp import FastMCP

# Create a named server
mcp = FastMCP("My App")

# Specify dependencies for deployment and development
mcp = FastMCP("My App", dependencies=["pandas", "numpy"])
```

### Resources

Resources are how you expose data to LLMs. They're similar to GET endpoints in a REST API - they provide data but shouldn't perform significant computation or have side effects. Some examples:

- File contents
- Database schemas
- API responses
- System information

Resources can be static:
```python
@mcp.resource("config://app")
def get_config() -> str:
    """Static configuration data"""
    return "App configuration here"
```

Or dynamic with parameters (FastMCP automatically handles these as MCP templates):
```python
@mcp.resource("users://{user_id}/profile")
def get_user_profile(user_id: str) -> str:
    """Dynamic user data"""
    return f"Profile data for user {user_id}"
```

### Tools

Tools let LLMs take actions through your server. Unlike resources, tools are expected to perform computation and have side effects. They're similar to POST endpoints in a REST API.

Simple calculation example:
```python
@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> float:
    """Calculate BMI given weight in kg and height in meters"""
    return weight_kg / (height_m ** 2)
```

HTTP request example:
```python
import httpx

@mcp.tool()
async def fetch_weather(city: str) -> str:
    """Fetch current weather for a city"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.weather.com/{city}"
        )
        return response.text
```

Complex input handling example:
```python
from pydantic import BaseModel, Field
from typing import Annotated

class ShrimpTank(BaseModel):
    class Shrimp(BaseModel):
        name: Annotated[str, Field(max_length=10)]

    shrimp: list[Shrimp]

@mcp.tool()
def name_shrimp(
    tank: ShrimpTank,
    # You can use pydantic Field in function signatures for validation.
    extra_names: Annotated[list[str], Field(max_length=10)],
) -> list[str]:
    """List all shrimp names in the tank"""
    return [shrimp.name for shrimp in tank.shrimp] + extra_names
```

### Prompts

Prompts are reusable templates that help LLMs interact with your server effectively. They're like "best practices" encoded into your server. A prompt can be as simple as a string:

```python
@mcp.prompt()
def review_code(code: str) -> str:
    return f"Please review this code:\n\n{code}"
```

Or a more structured sequence of messages:
```python
from fastmcp.prompts.base import UserMessage, AssistantMessage

@mcp.prompt()
def debug_error(error: str) -> list[Message]:
    return [
        UserMessage("I'm seeing this error:"),
        UserMessage(error),
        AssistantMessage("I'll help debug that. What have you tried so far?")
    ]
```


### Images

FastMCP provides an `Image` class that automatically handles image data in your server:

```python
from fastmcp import FastMCP, Image
from PIL import Image as PILImage

@mcp.tool()
def create_thumbnail(image_path: str) -> Image:
    """Create a thumbnail from an image"""
    img = PILImage.open(image_path)
    img.thumbnail((100, 100))
    
    # FastMCP automatically handles conversion and MIME types
    return Image(data=img.tobytes(), format="png")

@mcp.tool()
def load_image(path: str) -> Image:
    """Load an image from disk"""
    # FastMCP handles reading and format detection
    return Image(path=path)
```

Images can be used as the result of both tools and resources.

### Context

The Context object gives your tools and resources access to MCP capabilities. To use it, add a parameter annotated with `fastmcp.Context`:

```python
from fastmcp import FastMCP, Context

@mcp.tool()
async def long_task(files: list[str], ctx: Context) -> str:
    """Process multiple files with progress tracking"""
    for i, file in enumerate(files):
        ctx.info(f"Processing {file}")
        await ctx.report_progress(i, len(files))
        
        # Read another resource if needed
        data = await ctx.read_resource(f"file://{file}")
        
    return "Processing complete"
```

The Context object provides:
- Progress reporting through `report_progress()`
- Logging via `debug()`, `info()`, `warning()`, and `error()`
- Resource access through `read_resource()`
- Request metadata via `request_id` and `client_id`

## Running Your Server

There are three main ways to use your FastMCP server, each suited for different stages of development:

### Development Mode (Recommended for Building & Testing)

The fastest way to test and debug your server is with the MCP Inspector:

```bash
fastmcp dev server.py
```

This launches a web interface where you can:
- Test your tools and resources interactively
- See detailed logs and error messages
- Monitor server performance
- Set environment variables for testing

During development, you can:
- Add dependencies with `--with`: 
  ```bash
  fastmcp dev server.py --with pandas --with numpy
  ```
- Mount your local code for live updates:
  ```bash
  fastmcp dev server.py --with-editable .
  ```

### Claude Desktop Integration (For Regular Use)

Once your server is ready, install it in Claude Desktop to use it with Claude:

```bash
fastmcp install server.py
```

Your server will run in an isolated environment with:
- Automatic installation of dependencies specified in your FastMCP instance:
  ```python
  mcp = FastMCP("My App", dependencies=["pandas", "numpy"])
  ```
- Custom naming via `--name`:
  ```bash
  fastmcp install server.py --name "My Analytics Server"
  ```
- Environment variable management:
  ```bash
  # Set variables individually
  fastmcp install server.py -e API_KEY=abc123 -e DB_URL=postgres://...
  
  # Or load from a .env file
  fastmcp install server.py -f .env
  ```

### Direct Execution (For Advanced Use Cases)

For advanced scenarios like custom deployments or running without Claude, you can execute your server directly:

```python
from fastmcp import FastMCP

mcp = FastMCP("My App")

if __name__ == "__main__":
    mcp.run()
```

Run it with:
```bash
# Using the FastMCP CLI
fastmcp run server.py

# Or with Python/uv directly
python server.py
uv run python server.py
```


Note: When running directly, you are responsible for ensuring all dependencies are available in your environment. Any dependencies specified on the FastMCP instance are ignored.

Choose this method when you need:
- Custom deployment configurations
- Integration with other services
- Direct control over the server lifecycle

### Server Object Names

All FastMCP commands will look for a server object called `mcp`, `app`, or `server` in your file. If you have a different object name or multiple servers in one file, use the syntax `server.py:my_server`:

```bash
# Using a standard name
fastmcp run server.py

# Using a custom name
fastmcp run server.py:my_custom_server
```

## Examples

Here are a few examples of FastMCP servers. For more, see the `examples/` directory.

### Echo Server
A simple server demonstrating resources, tools, and prompts:

```python
from fastmcp import FastMCP

mcp = FastMCP("Echo")

@mcp.resource("echo://{message}")
def echo_resource(message: str) -> str:
    """Echo a message as a resource"""
    return f"Resource echo: {message}"

@mcp.tool()
def echo_tool(message: str) -> str:
    """Echo a message as a tool"""
    return f"Tool echo: {message}"

@mcp.prompt()
def echo_prompt(message: str) -> str:
    """Create an echo prompt"""
    return f"Please process this message: {message}"
```

### SQLite Explorer
A more complex example showing database integration:

```python
from fastmcp import FastMCP
import sqlite3

mcp = FastMCP("SQLite Explorer")

@mcp.resource("schema://main")
def get_schema() -> str:
    """Provide the database schema as a resource"""
    conn = sqlite3.connect("database.db")
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return "\n".join(sql[0] for sql in schema if sql[0])

@mcp.tool()
def query_data(sql: str) -> str:
    """Execute SQL queries safely"""
    conn = sqlite3.connect("database.db")
    try:
        result = conn.execute(sql).fetchall()
        return "\n".join(str(row) for row in result)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.prompt()
def analyze_table(table: str) -> str:
    """Create a prompt template for analyzing tables"""
    return f"""Please analyze this database table:
Table: {table}
Schema: 
{get_schema()}

What insights can you provide about the structure and relationships?"""
```

## Contributing

<details>

<summary><h3>Open Developer Guide</h3></summary>

### Prerequisites

FastMCP requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

### Installation

For development, we recommend installing FastMCP with development dependencies, which includes various utilities the maintainers find useful.

```bash
git clone https://github.com/jlowin/fastmcp.git
cd fastmcp
uv sync --frozen --extra dev
```

For running tests only (e.g., in CI), you only need the testing dependencies:

```bash
uv sync --frozen --extra tests
```

### Testing

Please make sure to test any new functionality. Your tests should be simple and atomic and anticipate change rather than cement complex patterns.

Run tests from the root directory:


```bash
pytest -vv
```

### Formatting

FastMCP enforces a variety of required formats, which you can automatically enforce with pre-commit. 

Install the pre-commit hooks:

```bash
pre-commit install
```

The hooks will now run on every commit (as well as on every PR). To run them manually:

```bash
pre-commit run --all-files
```

### Opening a Pull Request

Fork the repository and create a new branch:

```bash
git checkout -b my-branch
```

Make your changes and commit them:


```bash
git add . && git commit -m "My changes"
```

Push your changes to your fork:


```bash
git push origin my-branch
```

Feel free to reach out in a GitHub issue or discussion if you have any questions!

</details>
