# ruff: noqa: BLE001
"""
MCP Resources for Notes App Configuration and Metadata

These resources provide configuration, documentation, and metadata for AI agents.
"""

import json
from datetime import datetime

from fastmcp import Context, FastMCP


def register_notes_resources(mcp: FastMCP):
    """Register all notes app resources with the MCP server."""

    @mcp.resource("config://notes-app")
    async def notes_app_config(ctx: Context = None) -> str:
        """
        Configuration and API information for the notes app.
        """
        config = {
            "app_name": "FastAPI Notes App",
            "version": "1.0.0",
            "description": "A comprehensive note-taking and task management application",
            "api_base_url": "https://full-stack-fastapi-template-bvfx.onrender.com",
            "supported_features": [
                "Note creation and management",
                "Task tracking and completion",
                "Category organization",
                "Content search",
                "AI-powered assistance",
                "Productivity analytics",
            ],
            "authentication": {
                "type": "Bearer token",
                "note": "In production, would require proper JWT authentication",
            },
            "rate_limits": {
                "requests_per_minute": 60,
                "note": "Rate limiting implemented via Upstash Redis",
            },
            "data_models": {
                "Note": {
                    "fields": [
                        "id",
                        "title",
                        "content",
                        "category",
                        "created_at",
                        "updated_at",
                    ],
                    "required": ["title"],
                    "optional": ["content", "category"],
                },
                "Task": {
                    "fields": [
                        "id",
                        "title",
                        "description",
                        "status",
                        "priority",
                        "due_date",
                        "category",
                        "created_at",
                        "updated_at",
                    ],
                    "required": ["title"],
                    "statuses": ["todo", "in_progress", "done"],
                    "priorities": ["low", "medium", "high"],
                },
                "Category": {
                    "fields": ["id", "name", "description", "created_at", "updated_at"],
                    "required": ["name"],
                },
            },
        }

        if ctx:
            await ctx.info("Returning notes app configuration")

        return json.dumps(config, indent=2)

    @mcp.resource("guide://tool-usage")
    async def tool_usage_guide(ctx: Context = None) -> str:
        """
        Comprehensive guide for using the MCP tools effectively.
        """
        guide = """# MCP Tools Usage Guide

## Notes Management Tools

### create_note
Creates a new note with title, content, and optional category.
**Best practices:**
- Use descriptive, searchable titles
- Include relevant content for context
- Assign appropriate categories for organization

### get_notes
Retrieves notes with optional filtering and pagination.
**Parameters:**
- limit: Number of notes to retrieve (default: 50)
- offset: Skip number of notes for pagination

### update_note  
Updates an existing note's title, content, or category.
**Note:** Requires exact note ID for identification

### search_notes
Searches notes by title and content matching.
**Tips:**
- Use specific keywords for better results
- Search is case-insensitive
- Searches both title and content fields

## Task Management Tools

### create_task
Creates a new task with status tracking.
**Required:** title
**Optional:** description, status, priority, due_date, category

### complete_task
Marks a task as completed (status = "done").
**Usage:** Provide task ID to mark complete

### get_task_statistics
Provides comprehensive task analytics including completion rates and status distribution.

## Category Management Tools

### create_category
Creates organizational categories for notes.
**Best practices:**
- Use clear, descriptive names
- Avoid duplicate categories
- Add descriptions for clarity

### organize_note_into_category
Associates existing notes with categories.
**Requirements:** Valid note ID and category ID

## AI-Powered Tools

### chat_with_ai
Direct interaction with Gemini AI for assistance.
**Models available:** gemini-1.5-flash-latest, other Gemini models

### summarize_notes
AI-generated summaries of user notes.
**Features:**
- Can filter by category
- Provides key themes and insights
- Suggests organizational improvements

### generate_task_suggestions
Analyzes notes to suggest actionable tasks.
**Output:** Specific, prioritized task recommendations

### improve_note_content
AI-powered content improvement.
**Types:** grammar, clarity, structure, expand

## Analytics and Productivity Tools

### get_productivity_dashboard
Comprehensive productivity metrics and insights.
**Includes:**
- Activity trends
- Completion rates  
- Category distributions
- Daily activity patterns

### find_duplicate_notes
Identifies potentially duplicate content.
**Parameters:** 
- similarity_threshold: 0.0 to 1.0 (default: 0.8)

### get_overdue_tasks_report
Analyzes task deadlines and provides overdue/upcoming task reports.

### get_content_insights
Detailed content analysis including word counts, topics, and writing patterns.

## General Best Practices

1. **Start with get_productivity_dashboard** to understand current state
2. **Use search_notes** before creating new notes to avoid duplicates
3. **Leverage AI tools** for content improvement and task generation
4. **Organize with categories** for better information architecture
5. **Regular cleanup** using duplicate detection and content insights
"""

        if ctx:
            await ctx.info("Returning tool usage guide")

        return guide

    @mcp.resource("examples://workflows")
    async def example_workflows(ctx: Context = None) -> str:
        """
        Example workflows for common use cases.
        """
        workflows = """# Example MCP Workflows

## Workflow 1: New User Onboarding

1. **Get Overview**: `get_productivity_dashboard` 
2. **Analyze Content**: `get_content_insights`
3. **Create Organization**: `create_category` for main topics
4. **Organize Existing**: `organize_note_into_category` for key notes
5. **Generate Tasks**: `generate_task_suggestions` from notes

## Workflow 2: Daily Productivity Review

1. **Check Tasks**: `get_overdue_tasks_report`
2. **Review Activity**: `get_productivity_dashboard` (1-7 days)
3. **Complete Tasks**: `complete_task` for finished items
4. **Create New Tasks**: Based on new priorities
5. **Update Notes**: `improve_note_content` for important notes

## Workflow 3: Content Cleanup and Organization

1. **Find Duplicates**: `find_duplicate_notes` 
2. **Analyze Content**: `get_content_insights`
3. **Create Categories**: Based on content themes
4. **Organize Notes**: `organize_note_into_category`
5. **Improve Content**: `improve_note_content` for key notes

## Workflow 4: Research Project Management

1. **Create Category**: For research project
2. **Create Research Notes**: `create_note` for each source
3. **Generate Summary**: `summarize_notes` for project category
4. **Create Tasks**: `generate_task_suggestions` for next steps
5. **Track Progress**: Regular `get_task_statistics`

## Workflow 5: Weekly Planning Session

1. **Review Metrics**: `get_productivity_dashboard` (7-30 days)
2. **Check Overdue**: `get_overdue_tasks_report`  
3. **Analyze Content**: `get_content_insights`
4. **Plan Tasks**: Create tasks for upcoming priorities
5. **Organize Notes**: Update categories and improve content

## AI-Assisted Workflows

### Smart Content Creation
1. Start with `chat_with_ai` to brainstorm
2. Create initial notes with ideas
3. Use `improve_note_content` to refine
4. Generate tasks with `generate_task_suggestions`

### Intelligent Organization
1. Analyze with `get_content_insights`
2. Find patterns and themes
3. Create logical `create_category` structure
4. Use AI to `summarize_notes` by category
5. Organize systematically

### Productivity Optimization
1. Get baseline with `get_productivity_dashboard`
2. Identify bottlenecks in task completion
3. Use AI to suggest improvements
4. Implement changes and track progress
5. Regular review and adjustment
"""

        if ctx:
            await ctx.info("Returning example workflows")

        return workflows

    @mcp.resource("schema://api-reference")
    async def api_reference(ctx: Context = None) -> str:
        """
        API reference and data schemas for the notes app.
        """
        reference = {
            "api_version": "v1",
            "base_url": "https://full-stack-fastapi-template-bvfx.onrender.com/api/v1",
            "endpoints": {
                "notes": {
                    "GET /notes/": "List all notes",
                    "POST /notes/": "Create a new note",
                    "PUT /notes/{id}": "Update a note",
                    "DELETE /notes/{id}": "Delete a note",
                },
                "tasks": {
                    "GET /tasks/": "List all tasks",
                    "POST /tasks/": "Create a new task",
                    "PUT /tasks/{id}": "Update a task",
                    "DELETE /tasks/{id}": "Delete a task",
                },
                "categories": {
                    "GET /categories/": "List all categories",
                    "POST /categories/": "Create a new category",
                },
                "ai": {
                    "POST /gemini/chat": "Chat with Gemini AI",
                    "POST /gemini/embeddings": "Generate embeddings",
                },
            },
            "schemas": {
                "Note": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "title": {"type": "string", "required": True},
                        "content": {"type": "string"},
                        "category": {"$ref": "#/schemas/Category"},
                        "created_at": {"type": "string", "format": "datetime"},
                        "updated_at": {"type": "string", "format": "datetime"},
                    },
                },
                "Task": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "title": {"type": "string", "required": True},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["todo", "in_progress", "done"],
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "due_date": {"type": "string", "format": "datetime"},
                        "category": {"type": "string"},
                        "created_at": {"type": "string", "format": "datetime"},
                        "updated_at": {"type": "string", "format": "datetime"},
                    },
                },
                "Category": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "name": {"type": "string", "required": True},
                        "description": {"type": "string"},
                        "created_at": {"type": "string", "format": "datetime"},
                        "updated_at": {"type": "string", "format": "datetime"},
                    },
                },
            },
            "authentication": {
                "type": "bearer",
                "description": "Include JWT token in Authorization header",
                "example": "Authorization: Bearer <token>",
            },
            "error_responses": {
                "400": "Bad Request - Invalid input data",
                "401": "Unauthorized - Authentication required",
                "403": "Forbidden - Insufficient permissions",
                "404": "Not Found - Resource not found",
                "429": "Too Many Requests - Rate limit exceeded",
                "500": "Internal Server Error - Server error",
            },
        }

        if ctx:
            await ctx.info("Returning API reference")

        return json.dumps(reference, indent=2)

    @mcp.resource("status://health")
    async def health_status(ctx: Context = None) -> str:
        """
        Current health and status information.
        """
        status = {
            "mcp_server": "operational",
            "tools_registered": 23,  # Total count of all tools
            "prompts_available": 5,
            "resources_available": 5,
            "api_backend": "https://full-stack-fastapi-template-bvfx.onrender.com",
            "backend_status": "operational",  # Would check in real implementation
            "last_updated": datetime.utcnow().isoformat(),
            "capabilities": [
                "Notes CRUD operations",
                "Task management",
                "Category organization",
                "AI-powered assistance",
                "Productivity analytics",
                "Content insights",
                "Duplicate detection",
                "Task deadline tracking",
            ],
        }

        if ctx:
            await ctx.info("Returning health status")

        return json.dumps(status, indent=2)


if __name__ == "__main__":
    # This allows the module to be imported and register its resources
    pass
