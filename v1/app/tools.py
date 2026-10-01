"""LangChain tools for managing todos in the database."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool

from app.database import Todo, session_scope


def _format_todo(todo: Todo) -> str:
    desc = todo.description or "(no description)"
    created = todo.created_at.strftime("%Y-%m-%d %H:%M") if todo.created_at else "?"
    return (
        f"- [#{todo.id}] {todo.title} "
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
    with session_scope() as session:
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
    with session_scope() as session:
        todos = (
            session.query(Todo)
            .filter(Todo.title.ilike(term) | Todo.description.ilike(term))
            .order_by(Todo.created_at.desc())
            .all()
        )
        return _format_todos(todos)


@tool
def find_tasks(query: str, status: Optional[str] = "pending") -> str:
    """Find tasks whose title matches a query, optionally filtered by status.

    Args:
        query: Text to match against task titles (case-insensitive).
        status: Filter by task status. One of 'pending', 'in_progress',
            'completed'. Pass None to search all statuses. Defaults to
            'pending'.

    Returns:
        A markdown list of matching tasks, or a message if none match.
    """
    clean_query = query.strip()
    if not clean_query:
        return "Error: a non-empty query is required to search tasks."

    with session_scope() as session:
        q = session.query(Todo).filter(Todo.title.ilike(f"%{clean_query}%"))
        if status:
            q = q.filter(Todo.status == status.strip().lower())
        todos = q.order_by(Todo.created_at.desc()).all()
        if not todos:
            return f"No {status or ''} tasks found matching '{clean_query}'."
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

    clean_title = title.strip()
    clean_priority = (priority or "medium").strip().lower()
    with session_scope() as session:
        todo = Todo(
            title=clean_title,
            description=(description or "").strip() or None,
            priority=clean_priority,
            status="pending",
        )
        session.add(todo)
        session.flush()  # populate todo.id before the session closes
        new_id = todo.id
    return f"Added task #{new_id}: '{clean_title}' (priority: {clean_priority})."


@tool
def update_status(todo_id: int, status: str) -> str:
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

    with session_scope() as session:
        todo = session.get(Todo, todo_id)
        if todo is None:
            return f"Error: no task found with id #{todo_id}."
        todo.status = normalized
        title = todo.title
    return f"Updated task #{todo_id} ('{title}') to status '{normalized}'."


@tool
def update_task(
    task_id: int,
    priority: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """Update the priority and/or title of an existing task.

    Args:
        task_id: The numeric id of the task to update.
        priority: New priority. One of 'low', 'medium', 'high'. Omit to leave
            the priority unchanged.
        title: New title. Omit to leave the title unchanged.

    Returns:
        A confirmation message, or an error if the task or priority is invalid
        or nothing was changed.
    """
    new_priority = priority.strip().lower() if priority else None
    new_title = title.strip() if title else None
    if new_priority is None and not new_title:
        return "Error: provide at least one of priority or title to update."
    if new_priority is not None and new_priority not in {"low", "medium", "high"}:
        return f"Error: priority must be one of ['high', 'low', 'medium'], got '{priority}'."

    changes = []
    with session_scope() as session:
        todo = session.get(Todo, task_id)
        if todo is None:
            return f"Error: no task found with id #{task_id}."
        if new_priority is not None:
            todo.priority = new_priority
            changes.append(f"priority to '{new_priority}'")
        if new_title:
            todo.title = new_title
            changes.append(f"title to '{new_title}'")
        current_title = todo.title
    return f"Updated task #{task_id} ('{current_title}'): set {' and '.join(changes)}."


@tool
def delete_task(task_id: int) -> str:
    """Permanently delete a task from the database.

    Args:
        task_id: The numeric id of the task to delete.

    Returns:
        A confirmation message, or an error if no task matches the id.
    """
    with session_scope() as session:
        todo = session.get(Todo, task_id)
        if todo is None:
            return f"Error: no task found with id #{task_id}."
        title = todo.title
        session.delete(todo)
    return f"Deleted task #{task_id} ('{title}') permanently."


ALL_TOOLS = [
    get_todos,
    search_todos,
    find_tasks,
    add_todo,
    update_status,
    update_task,
    delete_task,
]
