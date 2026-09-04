# ruff: noqa: BLE001, F841
"""
Notes Management Tools for MCP Server

These tools allow AI agents to manage notes through the FastAPI backend.
"""

import json

from fastmcp import Context, FastMCP

try:
    from ..auth_utils import convert_user_id_to_token, make_authenticated_request
except ImportError:  # Standalone repository layout
    from auth_utils import convert_user_id_to_token, make_authenticated_request

# Import the MCP instance (will be imported in server.py)
# from app.model_context_protocol.server import mcp


def register_notes_tools(mcp: FastMCP):
    """Register all notes-related tools with the MCP server."""

    @mcp.tool()
    async def create_note(
        title: str,
        content: str = "",
        category_id: str | None = None,
        user_id: str = "demo-user",
        ctx: Context = None,
    ) -> str:
        """
        Create a new note with the given title and content.

        Args:
            title: The title of the note (required)
            content: The content/body of the note (optional)
            category_id: UUID of the category to assign the note to (optional)
            user_id: User ID or JWT token for authentication

        Returns:
            JSON string with the created note details
        """
        if ctx:
            await ctx.info(f"Creating note with title: {title}")

        try:
            # Convert user_id to proper JWT token
            jwt_token = await convert_user_id_to_token(user_id)

            note_data = {"title": title, "content": content}
            if category_id:
                note_data["category_id"] = category_id

            result = await make_authenticated_request(
                "POST", "/api/v1/notes/", jwt_token, note_data
            )

            if ctx:
                await ctx.info(f"Successfully created note with ID: {result.get('id')}")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to create note: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_notes(
        user_id: str = "demo-user", skip: int = 0, limit: int = 20, ctx: Context = None
    ) -> str:
        """
        Retrieve notes for the user.

        Args:
            user_id: User ID (default: demo-user)
            skip: Number of notes to skip (for pagination)
            limit: Maximum number of notes to return

        Returns:
            JSON string with list of notes
        """
        if ctx:
            await ctx.info(f"Retrieving notes for user: {user_id}")

        try:
            params = {"skip": skip, "limit": limit}
            result = await make_authenticated_request(
                "GET", "/api/v1/notes/", user_id, params=params
            )

            if ctx:
                await ctx.info(f"Retrieved {len(result.get('data', []))} notes")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to retrieve notes: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def update_note(
        note_id: str,
        title: str | None = None,
        content: str | None = None,
        category_id: str | None = None,
        user_id: str = "demo-user",
        ctx: Context = None,
    ) -> str:
        """
        Update an existing note.

        Args:
            note_id: UUID of the note to update
            title: New title for the note (optional)
            content: New content for the note (optional)
            category_id: New category ID for the note (optional)
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with the updated note details
        """
        if ctx:
            await ctx.info(f"Updating note: {note_id}")

        try:
            update_data = {}
            if title is not None:
                update_data["title"] = title
            if content is not None:
                update_data["content"] = content
            if category_id is not None:
                update_data["category_id"] = category_id

            result = await make_authenticated_request(
                "PUT", f"/api/v1/notes/{note_id}", user_id, update_data
            )

            if ctx:
                await ctx.info(f"Successfully updated note: {note_id}")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to update note: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def delete_note(
        note_id: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Delete a note by ID.

        Args:
            note_id: UUID of the note to delete
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with deletion confirmation
        """
        if ctx:
            await ctx.info(f"Deleting note: {note_id}")

        try:
            result = await make_authenticated_request(
                "DELETE", f"/api/v1/notes/{note_id}", user_id
            )

            if ctx:
                await ctx.info(f"Successfully deleted note: {note_id}")

            return json.dumps({"message": f"Note {note_id} deleted successfully"})

        except Exception as e:
            error_msg = f"Failed to delete note: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def search_notes(
        query: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Search notes by content or title.

        Args:
            query: Search query string
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with matching notes
        """
        if ctx:
            await ctx.info(f"Searching notes for query: {query}")

        try:
            # This would use your existing search endpoint or filter logic
            params = {"search": query}
            result = await make_authenticated_request(
                "GET", "/api/v1/notes/", user_id, params=params
            )

            # Filter results locally if needed (depends on your API implementation)
            notes = result.get("data", [])
            filtered_notes = [
                note
                for note in notes
                if query.lower() in note.get("title", "").lower()
                or query.lower() in note.get("content", "").lower()
            ]

            search_result = {
                "query": query,
                "matches": filtered_notes,
                "count": len(filtered_notes),
            }

            if ctx:
                await ctx.info(f"Found {len(filtered_notes)} matching notes")

            return json.dumps(search_result, default=str)

        except Exception as e:
            error_msg = f"Failed to search notes: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})
