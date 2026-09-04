# ruff: noqa: BLE001, E722
"""
AI Assistant Tools for MCP Server using Gemini

These tools allow AI agents to use Gemini for intelligent assistance with notes and tasks.
"""

import json
from datetime import datetime

from fastmcp import Context, FastMCP

try:
    from ..auth_utils import convert_user_id_to_token, make_authenticated_request
except ImportError:  # Standalone repository layout
    from auth_utils import convert_user_id_to_token, make_authenticated_request


def register_ai_tools(mcp: FastMCP):
    """Register all AI assistant tools with the MCP server."""

    @mcp.tool()
    async def chat_with_ai(
        message: str,
        user_id: str = "demo-user",
        model: str = "gemini-1.5-flash-latest",
        ctx: Context = None,
    ) -> str:
        """
        Chat with the AI assistant using Gemini.

        Args:
            message: The message to send to the AI
            user_id: User ID (default: demo-user)
            model: Gemini model to use (default: gemini-1.5-flash-latest)

        Returns:
            JSON string with the AI's response
        """
        if ctx:
            await ctx.info(f"Sending message to AI: {message[:50]}...")

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            chat_data = {
                "messages": [{"role": "user", "content": message}],
                "model": model,
                "stream": False,
            }

            result = await make_authenticated_request(
                "POST", "/api/v1/gemini/chat", token, chat_data
            )

            if ctx:
                await ctx.info("Received AI response")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to chat with AI: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def summarize_notes(
        user_id: str = "demo-user", category_id: str | None = None, ctx: Context = None
    ) -> str:
        """
        Use AI to summarize the user's notes, optionally filtered by category.

        Args:
            user_id: User ID (default: demo-user)
            category_id: Optional category ID to filter notes (optional)

        Returns:
            JSON string with AI-generated summary of notes
        """
        if ctx:
            await ctx.info(f"Generating AI summary of notes for user: {user_id}")

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            # Get notes
            params = {"limit": 1000}
            notes_result = await make_authenticated_request(
                "GET", "/api/v1/notes/", token, params=params
            )

            notes = notes_result.get("data", [])

            # Filter by category if specified
            if category_id:
                notes = [
                    note
                    for note in notes
                    if note.get("category", {}).get("id") == category_id
                ]

            if not notes:
                return json.dumps(
                    {"summary": "No notes found to summarize.", "note_count": 0}
                )

            # Prepare notes content for AI
            notes_content = []
            for note in notes:
                note_text = f"Title: {note.get('title', 'Untitled')}\n"
                if note.get("content"):
                    note_text += f"Content: {note.get('content')}\n"
                if note.get("category", {}).get("name"):
                    note_text += f"Category: {note.get('category', {}).get('name')}\n"
                note_text += f"Created: {note.get('created_at', 'Unknown')}\n"
                notes_content.append(note_text)

            # Create AI prompt
            prompt = f"""Please provide a comprehensive summary of these {len(notes)} notes. 
            Include key themes, topics, and any patterns you notice:

{chr(10).join(notes_content)}

Please provide:
1. A brief overview
2. Main topics/themes
3. Key insights
4. Any suggestions for organization or follow-up actions"""

            # Send to AI
            chat_data = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "gemini-1.5-flash-latest",
                "stream": False,
            }

            ai_result = await make_authenticated_request(
                "POST", "/api/v1/gemini/chat", token, chat_data
            )

            summary_result = {
                "note_count": len(notes),
                "category_filter": category_id,
                "ai_summary": ai_result.get("message", {}).get(
                    "content", "Failed to generate summary"
                ),
                "generated_at": datetime.utcnow().isoformat(),
            }

            if ctx:
                await ctx.info(f"Generated AI summary for {len(notes)} notes")

            return json.dumps(summary_result, default=str)

        except Exception as e:
            error_msg = f"Failed to summarize notes: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def generate_task_suggestions(
        user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Use AI to analyze notes and suggest tasks that should be created.

        Args:
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with AI-generated task suggestions
        """
        if ctx:
            await ctx.info(f"Generating AI task suggestions for user: {user_id}")

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            # Get notes and existing tasks
            notes_result = await make_authenticated_request(
                "GET", "/api/v1/notes/", token, params={"limit": 1000}
            )

            tasks_result = await make_authenticated_request(
                "GET", "/api/v1/tasks/", token, params={"limit": 1000}
            )

            notes = notes_result.get("data", [])
            tasks = tasks_result.get("data", [])

            if not notes:
                return json.dumps(
                    {
                        "suggestions": [],
                        "message": "No notes available to analyze for task suggestions.",
                    }
                )

            # Prepare content for AI analysis
            notes_content = []
            for note in notes:
                note_text = f"Title: {note.get('title', 'Untitled')}\n"
                if note.get("content"):
                    note_text += f"Content: {note.get('content')}\n"
                notes_content.append(note_text)

            existing_tasks = [task.get("title", "") for task in tasks]

            # Create AI prompt
            prompt = f"""Analyze these notes and suggest actionable tasks that could be created. 
            Consider what needs to be done, followed up on, or acted upon based on the note contents.

Notes to analyze:
{chr(10).join(notes_content)}

Existing tasks (don't duplicate these):
{chr(10).join(existing_tasks)}

Please suggest 3-7 specific, actionable tasks in JSON format like:
[
    {{
        "title": "Task title",
        "description": "Detailed description",
        "priority": "high|medium|low",
        "category": "work|personal|study|other"
    }}
]

Focus on tasks that are:
1. Specific and actionable
2. Not already covered by existing tasks
3. Based on the content and context of the notes
4. Reasonable in scope"""

            # Send to AI
            chat_data = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "gemini-1.5-flash-latest",
                "stream": False,
            }

            ai_result = await make_authenticated_request(
                "POST", "/api/v1/gemini/chat", token, chat_data
            )

            ai_content = ai_result.get("message", {}).get("content", "")

            # Try to extract JSON from AI response
            try:
                # Look for JSON array in the response
                import re

                json_match = re.search(r"\[.*\]", ai_content, re.DOTALL)
                if json_match:
                    suggestions = json.loads(json_match.group())
                else:
                    suggestions = []
            except:
                suggestions = []

            result = {
                "note_count": len(notes),
                "existing_task_count": len(tasks),
                "suggestions": suggestions,
                "ai_analysis": ai_content,
                "generated_at": datetime.utcnow().isoformat(),
            }

            if ctx:
                await ctx.info(f"Generated {len(suggestions)} task suggestions")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to generate task suggestions: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def improve_note_content(
        note_id: str,
        improvement_type: str = "grammar",
        user_id: str = "demo-user",
        ctx: Context = None,
    ) -> str:
        """
        Use AI to improve note content (grammar, clarity, structure, etc.).

        Args:
            note_id: UUID of the note to improve
            improvement_type: Type of improvement - grammar, clarity, structure, expand (default: grammar)
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with improved note content suggestions
        """
        if ctx:
            await ctx.info(f"Improving note content for note: {note_id}")

        valid_types = ["grammar", "clarity", "structure", "expand"]
        if improvement_type not in valid_types:
            error_msg = (
                f"Invalid improvement_type. Must be one of: {', '.join(valid_types)}"
            )
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            # Get the specific note
            notes_result = await make_authenticated_request(
                "GET", "/api/v1/notes/", token, params={"limit": 1000}
            )

            notes = notes_result.get("data", [])
            target_note = None
            for note in notes:
                if note.get("id") == note_id:
                    target_note = note
                    break

            if not target_note:
                return json.dumps({"error": f"Note with ID {note_id} not found"})

            # Create improvement prompt based on type
            improvement_prompts = {
                "grammar": "Please improve the grammar and spelling of this note while keeping the original meaning:",
                "clarity": "Please rewrite this note to make it clearer and more understandable:",
                "structure": "Please reorganize and restructure this note for better flow and readability:",
                "expand": "Please expand on this note with more details, examples, or related information:",
            }

            original_content = f"Title: {target_note.get('title', '')}\nContent: {target_note.get('content', '')}"
            prompt = f"{improvement_prompts[improvement_type]}\n\n{original_content}"

            # Send to AI
            chat_data = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "gemini-1.5-flash-latest",
                "stream": False,
            }

            ai_result = await make_authenticated_request(
                "POST", "/api/v1/gemini/chat", token, chat_data
            )

            result = {
                "note_id": note_id,
                "improvement_type": improvement_type,
                "original_title": target_note.get("title", ""),
                "original_content": target_note.get("content", ""),
                "improved_content": ai_result.get("message", {}).get("content", ""),
                "generated_at": datetime.utcnow().isoformat(),
            }

            if ctx:
                await ctx.info(
                    f"Generated improved content for note using {improvement_type} improvement"
                )

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to improve note content: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})
