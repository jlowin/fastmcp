#!/usr/bin/env python3
"""
Demo of the state snapshot functionality in FastMCP Context.
"""

from fastmcp import FastMCP
from fastmcp.server.context import Context

mcp = FastMCP("State Snapshot Demo")

@mcp.tool
def setup_user_data(username: str, theme: str, language: str, ctx: Context) -> str:
    """Set up some user preferences in the context state."""
    ctx.set_state("username", username)
    ctx.set_state("theme", theme)
    ctx.set_state("language", language)
    ctx.set_state("session_start", "2024-01-15T10:30:00Z")
    
    return f"User data set up for {username} (theme: {theme}, language: {language})"

@mcp.tool
def create_state_snapshot(snapshot_name: str, ctx: Context) -> str:
    """Create a named snapshot of the current context state."""
    return ctx.create_snapshot(snapshot_name)

@mcp.tool
def show_current_state(ctx: Context) -> dict:
    """Show all current state values."""
    # Get all state by accessing the internal _state dict
    current_state = {}
    for key in ["username", "theme", "language", "session_start", "temp_data"]:
        value = ctx.get_state(key)
        if value is not None:
            current_state[key] = value
    return current_state

@mcp.tool
def modify_state(key: str, value: str, ctx: Context) -> str:
    """Modify a state value."""
    ctx.set_state(key, value)
    return f"Set {key} = {value}"

@mcp.tool
def list_all_snapshots(ctx: Context) -> list[str]:
    """List all available snapshots."""
    return ctx.list_snapshots()

@mcp.tool
def restore_from_snapshot(snapshot_name: str, ctx: Context) -> str:
    """Restore state from a named snapshot."""
    try:
        return ctx.restore_snapshot(snapshot_name)
    except KeyError as e:
        return f"Error: {e}"

@mcp.tool
def delete_state_snapshot(snapshot_name: str, ctx: Context) -> str:
    """Delete a named snapshot."""
    try:
        return ctx.delete_snapshot(snapshot_name)
    except KeyError as e:
        return f"Error: {e}"

@mcp.tool
def get_snapshot_data(snapshot_name: str, ctx: Context) -> dict:
    """Get the data from a specific snapshot."""
    try:
        return ctx.get_snapshot(snapshot_name)
    except KeyError as e:
        return {"error": str(e)}

@mcp.tool
def compare_snapshots(snapshot1_name: str, snapshot2_name: str, ctx: Context) -> dict:
    """Compare two snapshots and show the differences."""
    try:
        return ctx.get_snapshot_diff(snapshot1_name, snapshot2_name)
    except KeyError as e:
        return {"error": str(e)}

# Example usage flow:
"""
1. setup_user_data("alice", "dark", "en") 
2. create_state_snapshot("initial_setup")
3. modify_state("theme", "light")
4. modify_state("temp_data", "some temporary value") 
5. create_state_snapshot("modified_state")
6. show_current_state() # shows modified state
7. get_snapshot_data("initial_setup") # shows original snapshot data
8. compare_snapshots("initial_setup", "modified_state") # shows the diff:
   # {
   #   "added": {"temp_data": "some temporary value"},
   #   "removed": {},
   #   "modified": {"theme": {"old": "dark", "new": "light"}},
   #   "unchanged": {"username": "alice", "language": "en", "session_start": "..."}
   # }
9. restore_from_snapshot("initial_setup")
10. show_current_state() # shows original state (no temp_data, theme=dark)
11. list_all_snapshots() # shows ["initial_setup", "modified_state"]
"""

if __name__ == "__main__":
    mcp.run()
