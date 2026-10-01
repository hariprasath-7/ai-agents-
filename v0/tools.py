"""LangChain tools for managing todos in the database."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool

from database import Todo, get_session


def _format_todo(todo: Todo) -> str:
    desc = todo.description or "(no description)"
    created = todo.created_at.strftime("%Y-%m-%d %H:%M") if todo.created_at else "?"
    return (
        f"- [#{todo.id}] **{todo.title}** "
        f"(status: {todo.status}, priority: {todo.priority}, created: {created})\n"
        f"    {desc}"
    )


def _format_todos(todos: list[Todo]) -> str:
    if not todos:
        return "No matching tasks found."
    return "\n".join(_format_todo(t) for t in todos)


@tool
def get_todos(status: Optional[str] = None, priority: Optional[str] = None) -> str:
    """Fetch todos, optionally filtered by status and/or priority.

    Args:
        status: Filter by task status. One of 'pending', 'in_progress',
            'completed'. Omit to include all statuses.
        priority: Filter by task priority. One of 'low', 'medium', 'high'.
            Omit to include all priorities.

    Returns:
        A markdown list of matching tasks, or a message if none match.
    """
    with get_session() as session:
        query = session.query(Todo)
        if status:
            query = query.filter(Todo.status == status.strip().lower())
        if priority:
            query = query.filter(Todo.priority == priority.strip().lower())
        todos = query.order_by(Todo.created_at.desc()).all()
        return _format_todos(todos)


@tool
def search_todos(keyword: str) -> str:
    """Search tasks whose title or description contains a keyword.

    Args:
        keyword: The text to search for (case-insensitive).

    Returns:
        A markdown list of matching tasks, or a message if none match.
    """
    term = f"%{keyword.strip()}%"
    with get_session() as session:
        todos = (
            session.query(Todo)
            .filter(Todo.title.ilike(term) | Todo.description.ilike(term))
            .order_by(Todo.created_at.desc())
            .all()
        )
        return _format_todos(todos)


@tool
def add_todo(
    title: str,
    description: Optional[str] = "",
    priority: Optional[str] = "medium",
) -> str:
    """Add a new task to the database.

    Args:
        title: Short title of the task (required).
        description: Optional longer description. Defaults to empty.
        priority: One of 'low', 'medium', 'high'. Defaults to 'medium'.

    Returns:
        A confirmation message including the new task's id.
    """
    if not title or not title.strip():
        return "Error: a non-empty title is required to add a task."

    with get_session() as session:
        todo = Todo(
            title=title.strip(),
            description=(description or "").strip() or None,
            priority=(priority or "medium").strip().lower(),
            status="pending",
        )
        session.add(todo)
        session.flush()  # populate todo.id before the session closes
        new_id = todo.id
    return f"Added task #{new_id}: '{title.strip()}' (priority: {priority})."


@tool
def update_todo_status(todo_id: int, status: str) -> str:
    """Update the status of an existing task.

    Args:
        todo_id: The numeric id of the task to update.
        status: New status. One of 'pending', 'in_progress', 'completed'.

    Returns:
        A confirmation message, or an error if the task or status is invalid.
    """
    valid = {"pending", "in_progress", "completed"}
    normalized = status.strip().lower()
    if normalized not in valid:
        return f"Error: status must be one of {sorted(valid)}, got '{status}'."

    with get_session() as session:
        todo = session.get(Todo, todo_id)
        if todo is None:
            return f"Error: no task found with id #{todo_id}."
        todo.status = normalized
        title = todo.title
    return f"Updated task #{todo_id} ('{title}') to status '{normalized}'."


ALL_TOOLS = [get_todos, search_todos, add_todo, update_todo_status]
