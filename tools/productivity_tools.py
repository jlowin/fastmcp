# ruff: noqa: BLE001, E722, S110, S112
"""
Productivity and Analytics Tools for MCP Server

These tools provide insights and productivity features for the notes app.
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastmcp import Context, FastMCP

try:
    from ..auth_utils import convert_user_id_to_token, make_authenticated_request
except ImportError:  # Standalone repository layout
    from auth_utils import convert_user_id_to_token, make_authenticated_request


def register_productivity_tools(mcp: FastMCP):
    """Register all productivity and analytics tools with the MCP server."""

    @mcp.tool()
    async def get_productivity_dashboard(
        user_id: str = "demo-user", days_back: int = 7, ctx: Context = None
    ) -> str:
        """
        Generate a comprehensive productivity dashboard with notes and tasks analytics.

        Args:
            user_id: User ID (default: demo-user)
            days_back: Number of days to analyze (default: 7)

        Returns:
            JSON string with productivity metrics and insights
        """
        if ctx:
            await ctx.info(f"Generating productivity dashboard for {days_back} days")

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)
            if not token:
                return json.dumps({"error": "Failed to get valid authentication token"})

            # Get all notes and tasks
            try:
                notes_result = await make_authenticated_request(
                    "GET", "/api/v1/notes/", token, params={"limit": 1000}
                )
                notes = (
                    notes_result.get("data", [])
                    if notes_result and isinstance(notes_result, dict)
                    else []
                )
                # Ensure notes is a list
                if not isinstance(notes, list):
                    notes = []
            except Exception as e:
                if ctx:
                    await ctx.error(f"Failed to fetch notes: {e}")
                notes = []

            try:
                tasks_result = await make_authenticated_request(
                    "GET", "/api/v1/tasks/", token, params={"limit": 1000}
                )
                tasks = (
                    tasks_result.get("data", [])
                    if tasks_result and isinstance(tasks_result, dict)
                    else []
                )
                # Ensure tasks is a list
                if not isinstance(tasks, list):
                    tasks = []
            except Exception as e:
                if ctx:
                    await ctx.error(f"Failed to fetch tasks: {e}")
                tasks = []

            # Calculate date range
            end_date = datetime.now(datetime.timezone.utc)
            start_date = end_date - timedelta(days=days_back)

            # Filter by date range
            recent_notes = []
            recent_tasks = []

            for note in notes:
                if note.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(
                            note["created_at"].replace("Z", "+00:00")
                        )
                        if created_at >= start_date:
                            recent_notes.append(note)
                    except:
                        pass

            for task in tasks:
                if task.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(
                            task["created_at"].replace("Z", "+00:00")
                        )
                        if created_at >= start_date:
                            recent_tasks.append(task)
                    except:
                        pass

            # Calculate metrics
            total_notes = len(notes)
            total_tasks = len(tasks)
            recent_notes_count = len(recent_notes)
            recent_tasks_count = len(recent_tasks)

            # Task completion metrics
            completed_tasks = [t for t in tasks if t.get("status") == "done"]
            recent_completed_tasks = [
                t for t in recent_tasks if t.get("status") == "done"
            ]

            completion_rate = len(completed_tasks) / len(tasks) * 100 if tasks else 0
            recent_completion_rate = (
                len(recent_completed_tasks) / len(recent_tasks) * 100
                if recent_tasks
                else 0
            )

            # Category distribution
            note_categories = Counter()
            task_categories = Counter()

            for note in notes:
                category_obj = note.get("category", {})
                if category_obj and isinstance(category_obj, dict):
                    category = category_obj.get("name", "Uncategorized")
                else:
                    category = "Uncategorized"
                note_categories[category] += 1

            for task in tasks:
                category = task.get("category", "Uncategorized")
                if not category:
                    category = "Uncategorized"
                task_categories[category] += 1

            # Task status distribution
            task_statuses = Counter(task.get("status", "unknown") for task in tasks)

            # Activity by day
            daily_activity = defaultdict(lambda: {"notes": 0, "tasks": 0})

            for note in recent_notes:
                if note.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(
                            note["created_at"].replace("Z", "+00:00")
                        )
                        day_key = created_at.strftime("%Y-%m-%d")
                        daily_activity[day_key]["notes"] += 1
                    except:
                        pass

            for task in recent_tasks:
                if task.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(
                            task["created_at"].replace("Z", "+00:00")
                        )
                        day_key = created_at.strftime("%Y-%m-%d")
                        daily_activity[day_key]["tasks"] += 1
                    except:
                        pass

            dashboard = {
                "period": {
                    "days_analyzed": days_back,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "summary": {
                    "total_notes": total_notes,
                    "total_tasks": total_tasks,
                    "recent_notes": recent_notes_count,
                    "recent_tasks": recent_tasks_count,
                    "notes_per_day": round(recent_notes_count / days_back, 2),
                    "tasks_per_day": round(recent_tasks_count / days_back, 2),
                },
                "task_completion": {
                    "total_completed": len(completed_tasks),
                    "recent_completed": len(recent_completed_tasks),
                    "overall_completion_rate": round(completion_rate, 2),
                    "recent_completion_rate": round(recent_completion_rate, 2),
                    "status_distribution": dict(task_statuses),
                },
                "categories": {
                    "note_categories": dict(note_categories.most_common(10)),
                    "task_categories": dict(task_categories.most_common(10)),
                },
                "daily_activity": dict(daily_activity),
                "generated_at": datetime.now(datetime.timezone.utc).isoformat(),
            }

            if ctx:
                await ctx.info(
                    f"Generated dashboard with {total_notes} notes and {total_tasks} tasks"
                )

            return json.dumps(dashboard, default=str)

        except Exception as e:
            error_msg = f"Failed to generate productivity dashboard: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
                # Log the full traceback for debugging
                import traceback

                await ctx.error(f"Full traceback: {traceback.format_exc()}")
            # Also print to console for debugging
            import traceback

            print(f"❌ Productivity Dashboard Error: {error_msg}")
            print(f"Full traceback: {traceback.format_exc()}")
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def find_duplicate_notes(
        user_id: str = "demo-user",
        similarity_threshold: float = 0.8,
        ctx: Context = None,
    ) -> str:
        """
        Find potential duplicate notes based on title and content similarity.

        Args:
            user_id: User ID (default: demo-user)
            similarity_threshold: Similarity threshold between 0 and 1 (default: 0.8)

        Returns:
            JSON string with potential duplicate notes grouped together
        """
        if ctx:
            await ctx.info(
                f"Finding duplicate notes with {similarity_threshold} threshold"
            )

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            notes_result = await make_authenticated_request(
                "GET", "/api/v1/notes/", token, params={"limit": 1000}
            )

            notes = notes_result.get("data", [])

            if len(notes) < 2:
                return json.dumps(
                    {
                        "duplicates": [],
                        "message": "Not enough notes to check for duplicates",
                    }
                )

            # Simple similarity calculation using word overlap
            def calculate_similarity(note1: dict, note2: dict) -> float:
                # Combine title and content
                text1 = (
                    note1.get("title", "") + " " + note1.get("content", "")
                ).lower()
                text2 = (
                    note2.get("title", "") + " " + note2.get("content", "")
                ).lower()

                if not text1.strip() or not text2.strip():
                    return 0.0

                # Simple word-based similarity
                words1 = set(text1.split())
                words2 = set(text2.split())

                if not words1 or not words2:
                    return 0.0

                intersection = words1.intersection(words2)
                union = words1.union(words2)

                return len(intersection) / len(union) if union else 0.0

            # Find potential duplicates
            duplicates = []
            checked_pairs = set()

            for i, note1 in enumerate(notes):
                for j, note2 in enumerate(notes[i + 1 :], i + 1):
                    pair_key = tuple(sorted([note1.get("id"), note2.get("id")]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    similarity = calculate_similarity(note1, note2)

                    if similarity >= similarity_threshold:
                        duplicates.append(
                            {
                                "similarity_score": round(similarity, 3),
                                "notes": [
                                    {
                                        "id": note1.get("id"),
                                        "title": note1.get("title", "Untitled"),
                                        "content_preview": (
                                            note1.get("content", "") or ""
                                        )[:100]
                                        + "..."
                                        if len(note1.get("content", "") or "") > 100
                                        else note1.get("content", ""),
                                        "created_at": note1.get("created_at"),
                                        "category": note1.get("category", {}).get(
                                            "name"
                                        )
                                        if note1.get("category")
                                        else None,
                                    },
                                    {
                                        "id": note2.get("id"),
                                        "title": note2.get("title", "Untitled"),
                                        "content_preview": (
                                            note2.get("content", "") or ""
                                        )[:100]
                                        + "..."
                                        if len(note2.get("content", "") or "") > 100
                                        else note2.get("content", ""),
                                        "created_at": note2.get("created_at"),
                                        "category": note2.get("category", {}).get(
                                            "name"
                                        )
                                        if note2.get("category")
                                        else None,
                                    },
                                ],
                            }
                        )

            # Sort by similarity score descending
            duplicates.sort(key=lambda x: x["similarity_score"], reverse=True)

            result = {
                "total_notes_analyzed": len(notes),
                "similarity_threshold": similarity_threshold,
                "duplicate_groups_found": len(duplicates),
                "duplicates": duplicates[:20],  # Limit to top 20
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            if ctx:
                await ctx.info(f"Found {len(duplicates)} potential duplicate groups")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to find duplicate notes: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_overdue_tasks_report(
        user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Generate a report of overdue and upcoming tasks.

        Args:
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with overdue and upcoming tasks analysis
        """
        if ctx:
            await ctx.info("Generating overdue tasks report")

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            tasks_result = await make_authenticated_request(
                "GET", "/api/v1/tasks/", token, params={"limit": 1000}
            )

            tasks = tasks_result.get("data", [])

            if not tasks:
                return json.dumps(
                    {
                        "overdue_tasks": [],
                        "upcoming_tasks": [],
                        "message": "No tasks found",
                    }
                )

            now = datetime.now(timezone.utc)
            overdue_tasks = []
            upcoming_tasks = []

            for task in tasks:
                # Skip completed tasks
                if task.get("status") == "done":
                    continue

                # Check if task has a due date
                due_date_str = task.get("due_date")
                if not due_date_str:
                    continue

                try:
                    due_date = datetime.fromisoformat(
                        due_date_str.replace("Z", "+00:00")
                    )

                    task_info = {
                        "id": task.get("id"),
                        "title": task.get("title", "Untitled"),
                        "description": task.get("description", ""),
                        "status": task.get("status"),
                        "priority": task.get("priority", "medium"),
                        "category": task.get("category"),
                        "due_date": due_date_str,
                        "days_difference": (due_date - now).days,
                        "created_at": task.get("created_at"),
                    }

                    if due_date < now:
                        task_info["days_overdue"] = (now - due_date).days
                        overdue_tasks.append(task_info)
                    elif due_date <= now + timedelta(days=7):  # Due within a week
                        upcoming_tasks.append(task_info)

                except Exception:
                    # Skip tasks with invalid date formats
                    continue

            # Sort overdue tasks by how overdue they are (most overdue first)
            overdue_tasks.sort(key=lambda x: x.get("days_overdue", 0), reverse=True)

            # Sort upcoming tasks by due date (soonest first)
            upcoming_tasks.sort(key=lambda x: x["days_difference"])

            # Calculate summary stats
            total_active_tasks = len([t for t in tasks if t.get("status") != "done"])

            result = {
                "summary": {
                    "total_active_tasks": total_active_tasks,
                    "overdue_count": len(overdue_tasks),
                    "upcoming_count": len(upcoming_tasks),
                    "overdue_percentage": round(
                        len(overdue_tasks) / total_active_tasks * 100, 2
                    )
                    if total_active_tasks
                    else 0,
                },
                "overdue_tasks": overdue_tasks,
                "upcoming_tasks": upcoming_tasks,
                "recommendations": _generate_task_recommendations(
                    overdue_tasks, upcoming_tasks
                ),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            if ctx:
                await ctx.info(
                    f"Found {len(overdue_tasks)} overdue and {len(upcoming_tasks)} upcoming tasks"
                )

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to generate overdue tasks report: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    def _generate_task_recommendations(
        overdue_tasks: list[dict], upcoming_tasks: list[dict]
    ) -> list[str]:
        """Generate recommendations based on overdue and upcoming tasks."""
        recommendations = []

        if len(overdue_tasks) > 5:
            recommendations.append(
                "You have many overdue tasks. Consider reviewing and prioritizing them."
            )

        if overdue_tasks:
            high_priority_overdue = [
                t for t in overdue_tasks if t.get("priority") == "high"
            ]
            if high_priority_overdue:
                recommendations.append(
                    f"You have {len(high_priority_overdue)} high-priority overdue tasks that need immediate attention."
                )

        if upcoming_tasks:
            urgent_upcoming = [
                t for t in upcoming_tasks if t.get("days_difference", 0) <= 2
            ]
            if urgent_upcoming:
                recommendations.append(
                    f"You have {len(urgent_upcoming)} tasks due within 2 days."
                )

        if not overdue_tasks and not upcoming_tasks:
            recommendations.append("Great job! No overdue or urgent tasks found.")

        return recommendations

    @mcp.tool()
    async def get_content_insights(
        user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Analyze notes content to provide insights about writing patterns and topics.

        Args:
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with content analysis and insights
        """
        if ctx:
            await ctx.info("Generating content insights")

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            notes_result = await make_authenticated_request(
                "GET", "/api/v1/notes/", token, params={"limit": 1000}
            )

            notes = notes_result.get("data", [])

            if not notes:
                return json.dumps(
                    {"insights": {}, "message": "No notes found to analyze"}
                )

            # Content analysis
            total_notes = len(notes)
            total_words = 0
            total_chars = 0
            word_frequency = Counter()
            note_lengths = []
            categories = Counter()

            for note in notes:
                title = note.get("title", "") or ""
                content = note.get("content", "") or ""
                combined_text = (title + " " + content).lower()

                # Word count and character count
                words = combined_text.split()
                note_length = len(words)
                note_lengths.append(note_length)
                total_words += note_length
                total_chars += len(combined_text)

                # Word frequency (filter out common words)
                common_words = {
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                    "is",
                    "are",
                    "was",
                    "were",
                    "be",
                    "been",
                    "have",
                    "has",
                    "had",
                    "do",
                    "does",
                    "did",
                    "will",
                    "would",
                    "could",
                    "should",
                    "may",
                    "might",
                    "can",
                    "this",
                    "that",
                    "these",
                    "those",
                    "i",
                    "you",
                    "he",
                    "she",
                    "it",
                    "we",
                    "they",
                    "me",
                    "him",
                    "her",
                    "us",
                    "them",
                }
                for word in words:
                    if len(word) > 2 and word not in common_words:
                        word_frequency[word] += 1

                # Category distribution
                category_name = (
                    note.get("category", {}).get("name", "Uncategorized")
                    if note.get("category")
                    else "Uncategorized"
                )
                categories[category_name] += 1

            # Calculate statistics
            avg_words_per_note = total_words / total_notes if total_notes else 0
            avg_chars_per_note = total_chars / total_notes if total_notes else 0

            # Note length distribution
            if note_lengths:
                note_lengths.sort()
                median_length = note_lengths[len(note_lengths) // 2]
                shortest = min(note_lengths)
                longest = max(note_lengths)
            else:
                median_length = shortest = longest = 0

            # Get top topics (most frequent words)
            top_topics = dict(word_frequency.most_common(20))

            insights = {
                "content_statistics": {
                    "total_notes": total_notes,
                    "total_words": total_words,
                    "total_characters": total_chars,
                    "average_words_per_note": round(avg_words_per_note, 2),
                    "average_characters_per_note": round(avg_chars_per_note, 2),
                },
                "note_length_distribution": {
                    "shortest_note_words": shortest,
                    "longest_note_words": longest,
                    "median_note_words": median_length,
                    "average_note_words": round(avg_words_per_note, 2),
                },
                "top_topics": top_topics,
                "category_distribution": dict(categories),
                "writing_patterns": {
                    "notes_with_no_content": len(
                        [n for n in notes if not (n.get("content", "") or "").strip()]
                    ),
                    "notes_with_long_content": len(
                        [
                            n
                            for n in notes
                            if len((n.get("content", "") or "").split())
                            > avg_words_per_note * 2
                        ]
                    ),
                    "notes_with_short_content": len(
                        [
                            n
                            for n in notes
                            if len((n.get("content", "") or "").split())
                            < avg_words_per_note / 2
                        ]
                    ),
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            if ctx:
                await ctx.info(
                    f"Analyzed {total_notes} notes with {total_words} total words"
                )

            return json.dumps(insights, default=str)

        except Exception as e:
            error_msg = f"Failed to generate content insights: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})
