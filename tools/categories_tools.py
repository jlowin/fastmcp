# ruff: noqa: BLE001, F401
"""
Categories Management Tools for MCP Server

These tools allow AI agents to manage note categories through the FastAPI backend.
"""

import json

from fastmcp import Context, FastMCP

try:
    from ..auth_utils import convert_user_id_to_token, make_authenticated_request
except ImportError:  # Standalone repository layout
    from auth_utils import make_authenticated_request


def register_categories_tools(mcp: FastMCP):
    """Register all categories-related tools with the MCP server."""

    @mcp.tool()
    async def create_category(
        name: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Create a new category for organizing notes.

        Args:
            name: The name of the category (required)
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with the created category details
        """
        if ctx:
            await ctx.info(f"Creating category with name: {name}")

        try:
            category_data = {"name": name}

            result = await make_authenticated_request(
                "POST", "/api/v1/notes/categories", user_id, category_data
            )

            if ctx:
                await ctx.info(
                    f"Successfully created category with ID: {result.get('id')}"
                )

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to create category: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_categories(user_id: str = "demo-user", ctx: Context = None) -> str:
        """
        Retrieve all categories for the user.

        Args:
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with list of categories
        """
        if ctx:
            await ctx.info(f"Retrieving categories for user: {user_id}")

        try:
            result = await make_authenticated_request(
                "GET", "/api/v1/notes/categories", user_id
            )

            if ctx:
                await ctx.info(f"Retrieved {len(result)} categories")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to retrieve categories: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_notes_by_category(
        category_id: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Get all notes that belong to a specific category.

        Args:
            category_id: UUID of the category
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with notes in the category
        """
        if ctx:
            await ctx.info(f"Getting notes for category: {category_id}")

        try:
            # First get all notes
            result = await make_authenticated_request(
                "GET", "/api/v1/notes/", user_id, params={"limit": 1000}
            )

            # Filter by category
            all_notes = result.get("data", [])
            category_notes = [
                note
                for note in all_notes
                if note.get("category", {}).get("id") == category_id
            ]

            filtered_result = {
                "category_id": category_id,
                "notes": category_notes,
                "count": len(category_notes),
            }

            if ctx:
                await ctx.info(f"Found {len(category_notes)} notes in category")

            return json.dumps(filtered_result, default=str)

        except Exception as e:
            error_msg = f"Failed to get notes by category: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def organize_note_into_category(
        note_id: str, category_id: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Assign a note to a category (organize note).

        Args:
            note_id: UUID of the note to organize
            category_id: UUID of the category to assign the note to
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with the updated note details
        """
        if ctx:
            await ctx.info(f"Organizing note {note_id} into category {category_id}")

        try:
            update_data = {"category_id": category_id}

            result = await make_authenticated_request(
                "PUT", f"/api/v1/notes/{note_id}", user_id, update_data
            )

            if ctx:
                await ctx.info("Successfully organized note into category")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to organize note into category: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_category_summary(
        user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Get a summary of all categories with note counts.

        Args:
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with category summary including note counts
        """
        if ctx:
            await ctx.info(f"Getting category summary for user: {user_id}")

        try:
            # Get categories and notes
            categories_result = await make_authenticated_request(
                "GET", "/api/v1/notes/categories", user_id
            )

            notes_result = await make_authenticated_request(
                "GET", "/api/v1/notes/", user_id, params={"limit": 1000}
            )

            categories = categories_result
            notes = notes_result.get("data", [])

            # Count notes per category
            summary = []
            for category in categories:
                category_id = category["id"]
                note_count = len(
                    [
                        note
                        for note in notes
                        if note.get("category", {}).get("id") == category_id
                    ]
                )

                summary.append(
                    {
                        "id": category_id,
                        "name": category["name"],
                        "note_count": note_count,
                    }
                )

            # Count uncategorized notes
            uncategorized_count = len(
                [
                    note
                    for note in notes
                    if not note.get("category")
                    or not note.get("category", {}).get("id")
                ]
            )

            result = {
                "categories": summary,
                "total_categories": len(categories),
                "uncategorized_notes": uncategorized_count,
                "total_notes": len(notes),
            }

            if ctx:
                await ctx.info(
                    f"Generated summary: {len(categories)} categories, {len(notes)} total notes"
                )

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to get category summary: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})
