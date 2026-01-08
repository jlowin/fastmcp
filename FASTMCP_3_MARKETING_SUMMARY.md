# FastMCP 3.0 - Marketing Summary

**Audience:** Marketing team
**Purpose:** Highlight what to focus on for FastMCP 3.0 messaging

---

## Headline Features

### 1. File-Based MCP Servers (Coming Soon)

Define MCP servers using directory structure, similar to Next.js file-based routing. Drop a file in a folder and it becomes a tool, resource, or prompt - no manual registration required.

```
my_server/
├── tools/
│   ├── search.py      # becomes "search" tool
│   └── analyze.py     # becomes "analyze" tool
├── resources/
│   └── config.py      # becomes a resource
└── prompts/
    └── greeting.py    # becomes "greeting" prompt
```

**Why it matters:** Dramatically lower barrier to entry. New developers can build MCP servers without learning the framework first.

---

### 2. Composable Provider Architecture

Servers can now be stacked, transformed, and composed in ways that weren't possible before. Mount a server, apply a namespace, add transformations - all chainable.

```python
# Compose servers with transformations
provider = (
    FastMCPProvider(server)
    .with_namespace("api")
    .with_transforms(tool_renames={"verbose_name": "short"})
)
main.add_provider(provider)
```

**Why it matters:** Build modular MCP applications. Teams can develop components independently and compose them at runtime.

---

### 3. Strict Type Safety Throughout

New canonical types (`ToolResult`, `ResourceResult`, `PromptResult`, `Message`) provide compile-time safety. Errors caught during development instead of at runtime.

```python
from fastmcp.prompts import Message

@mcp.prompt
def greet(name: str) -> Message:
    return Message(f"Hello, {name}!")  # Auto-serializes, type-checked
```

**Why it matters:** Faster development feedback loop. Your IDE catches mistakes before your users do.

---

### 4. Simpler Auth Providers

All auth providers (GitHub, Google, Azure, AWS, Auth0, WorkOS, Descope, Discord, Scalekit, Supabase, OCI) have been streamlined with ~70% less code. Explicit configuration replaces magic environment variables.

```python
# Clear, explicit configuration
auth = GitHubProvider(
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
)
```

**Why it matters:** Easier to understand, debug, and deploy. No more hunting for undocumented environment variables.

---

## Additional Notable Changes

### Developer Experience
- **New visibility system** - Enable/disable components by key or tag at server level, hierarchical filtering that works reliably through provider chains
- **Cleaner prompt API** - `Message("Hello")` instead of verbose `PromptMessage(role="user", content=TextContent(type="text", text="Hello"))`
- **Semantic parameter names** - `get_tool(name=...)` instead of generic `get_tool(key=...)`

### Performance & Architecture
- **Parallel provider execution** - Component listing and execution now parallelized across providers
- **Lazy imports** - DiskStore no longer requires sqlite3 at import time
- **Unified execution model** - Components own their execution, consistent middleware handling

### API Improvements
- **`mount(namespace=...)` parameter** - Replaces `prefix` for clearer naming
- **Server banner control** - `FASTMCP_SHOW_SERVER_BANNER` applies to all startup methods
- **Supabase custom auth routes** - Support for custom authentication endpoints

### Bug Fixes & Stability
- OAuth token TTL and refresh handling improvements
- Client HTTP 4xx/5xx error handling fixed (no more hangs)
- MCP spec compliance improvements (enum schemas, error codes)
- Better $ref schema dereferencing for MCP client compatibility

---

## Under the Hood (Backend Improvements)

The majority of 3.0 changes are internal architecture improvements that make FastMCP more maintainable and performant:

- **Provider-based architecture** - Unified component sourcing through providers (`LocalProvider`, `FastMCPProvider`, `ProxyProvider`, `TransformingProvider`)
- **Removed code duplication** - Consolidated execution chains, eliminated redundant list methods
- **Explicit over implicit** - Replaced context variables with explicit `task_meta` parameters
- **Test infrastructure** - Converted to direct server calls, better async handling
- **Auth provider consolidation** - Reduced auth provider code by ~735 lines while maintaining functionality

---

## What's NOT in 3.0

- FastMCP Studio (UI) - Planned for future release

---

## Key Messaging Points

1. **"Convention over configuration"** - File-based servers make MCP accessible to everyone
2. **"Compose, don't configure"** - Modular server architecture enables team collaboration
3. **"Catch errors earlier"** - Type safety throughout the stack
4. **"Simpler auth, same power"** - Streamlined providers with explicit configuration
5. **"Production-ready"** - Performance improvements and battle-tested reliability

---

## Version Comparison

| Feature | 2.x | 3.0 |
|---------|-----|-----|
| Server composition | Basic mounting | Composable providers |
| Component types | Loose typing | Strict canonical types |
| Auth providers | Magic env vars | Explicit configuration |
| Visibility control | Mutable component state | Server-level filtering |
| Prompt API | Verbose MCP types | Simple `Message` class |
| Provider execution | Sequential | Parallelized |
| File-based servers | No | Yes |
