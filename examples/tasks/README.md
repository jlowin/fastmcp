# FastMCP Tasks Example

This example demonstrates FastMCP's background task execution using Docket, with progress tracking and multiple execution modes.

## Features

- **Background Tasks**: Execute long-running operations asynchronously
- **Progress Tracking**: Real-time progress updates via Docket
- **Flexible Backends**: Use in-memory (development) or Redis (production)
- **Client Modes**: Execute immediately or as background tasks
- **CLI Management**: Use `fastmcp tasks` commands to manage tasks

## Quick Start

### 1. Install Dependencies

```bash
# From the fastmcp root directory
uv sync
```

### 2. Start Redis

```bash
cd examples/tasks
docker compose up -d
```

### 3. Enable Environment

If you have [direnv](https://direnv.net/) installed:

```bash
direnv allow  # Automatically loads environment from .envrc
```

Or source the `.envrc` file directly:

```bash
source .envrc  # Loads environment variables into current shell
```

### 4. Run the Server

```bash
fastmcp run server.py
```

The server will connect to Redis on port 24242 and be ready for distributed task execution.

### Alternative: Single-Process Mode

If you want to try the example without Redis (single-process only):

```bash
# Update .envrc to use memory:// (uncomment the memory:// line)
# Or export manually:
export FASTMCP_EXPERIMENTAL_ENABLE_DOCKET=true
export FASTMCP_EXPERIMENTAL_ENABLE_TASKS=true
export FASTMCP_EXPERIMENTAL_DOCKET_URL=memory://

# Run server
fastmcp run server.py
```

Note: The `fastmcp tasks` CLI commands won't work in single-process mode.

## Using the Client

The example client demonstrates both immediate and background task execution:

### Background Task with Progress Callbacks (Default)

Submits a task and receives real-time progress updates via callbacks while
the client does other work:

```bash
python examples/tasks/client.py --duration 10
```

The client registers a callback that prints progress messages as they arrive,
demonstrates doing other work while the task runs, then waits for the final result.

### Immediate Execution

Blocks until the tool completes:

```bash
python examples/tasks/client.py immediate --duration 5
```

## Using the fastmcp tasks CLI

When using a Redis backend, you can start additional workers:

```bash
# Start an additional worker to process tasks in parallel
fastmcp tasks worker server.py

# Worker configuration is controlled via environment variables
# For example, to adjust concurrency:
export FASTMCP_EXPERIMENTAL_DOCKET_CONCURRENCY=20
fastmcp tasks worker server.py
```

**Note**: The `fastmcp tasks` CLI requires a distributed backend (Redis/Valkey) since it runs in a separate process. It won't work with the default `memory://` backend.

## Architecture

### Server (`server.py`)

- Creates a FastMCP server with a single async tool: `slow_computation`
- Tool sleeps for configurable duration (1-60 seconds)
- Uses `Progress()` dependency for real-time progress tracking
- Logs progress every 1-2 seconds
- Marked with `task=True` to support background execution

### Client (`client.py`)

- Demonstrates two execution modes:
  - **Immediate**: Blocks until tool completes
  - **Background**: Returns task ID immediately, optionally polls for progress
- Uses in-memory transport to connect directly to server instance
- Shows progress messages when polling

### Backend Options

- **memory://** (default): In-memory, single-process only
- **redis://**: Distributed, multi-process, survives restarts (works with Redis or Valkey)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FASTMCP_EXPERIMENTAL_ENABLE_DOCKET` | `false` | Enable Docket task system |
| `FASTMCP_EXPERIMENTAL_ENABLE_TASKS` | `false` | Enable MCP task protocol (SEP-1686) |
| `FASTMCP_EXPERIMENTAL_DOCKET_URL` | `memory://` | Docket backend URL |

## Learn More

- [FastMCP Tasks Documentation](https://gofastmcp.com/docs/tasks)
- [Docket Documentation](https://github.com/PrefectHQ/docket)
- [MCP Task Protocol (SEP-1686)](https://spec.modelcontextprotocol.io/specification/architecture/tasks/)
