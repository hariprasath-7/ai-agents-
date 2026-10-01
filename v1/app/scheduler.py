"""Background reminder worker for due-date alerts.

Polls the database every ``REMINDER_INTERVAL_SECONDS`` for pending tasks whose
``due_date`` has passed and pushes a one-time Telegram alert for each, guarded
by the ``reminded`` flag so no task is ever announced twice.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import Todo, session_scope
from app.telegram import build_task_keyboard, send_message
from app.tools import USER_TZ

logger = logging.getLogger(__name__)

REMINDER_INTERVAL_SECONDS = 30

# Most recent chat that messaged the bot; used as the reminder destination
# when DEFAULT_TELEGRAM_CHAT_ID is not configured.
_last_active_chat_id: int | None = None


def record_active_chat(chat_id: int) -> None:
    """Remember the most recent chat id seen on the webhook."""
    global _last_active_chat_id
    _last_active_chat_id = chat_id


def _resolve_chat_id() -> int | None:
    """Pick the chat to alert: env override wins, then the last active chat."""
    raw = settings.default_telegram_chat_id
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                "DEFAULT_TELEGRAM_CHAT_ID %r is not an integer; ignoring it.", raw
            )
    return _last_active_chat_id


def _fetch_due_tasks() -> list[dict[str, Any]]:
    """Blocking query for pending tasks that are due and not yet reminded."""
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        rows = (
            session.query(Todo)
            .filter(
                Todo.due_date.isnot(None),
                Todo.due_date <= now,
                Todo.status == "pending",
                Todo.reminded.is_(False),
            )
            .order_by(Todo.due_date.asc())
            .all()
        )
        return [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due_date": t.due_date,
            }
            for t in rows
        ]


def _mark_reminded(task_id: int) -> None:
    """Flip the reminded flag so the alert is never sent twice."""
    with session_scope() as session:
        todo = session.get(Todo, task_id)
        if todo is not None:
            todo.reminded = True


def _reminder_text(task: dict[str, Any]) -> str:
    due = task["due_date"].astimezone(USER_TZ).strftime("%d %b %Y, %H:%M")
    return (
        f"⏰ <b>Task Reminder!</b> [#{task['id']}]\n"
        f"<b>Task:</b> <code>{task['title']}</code>\n"
        f"<b>Due:</b> <code>{due}</code>\n"
        f"<b>Priority:</b> {task['priority'].capitalize()}"
    )


async def check_reminders_loop() -> None:
    """Run forever, alerting on newly-due tasks every 30 seconds."""
    while True:
        try:
            due_tasks = await run_in_threadpool(_fetch_due_tasks)
            if due_tasks:
                chat_id = _resolve_chat_id()
                if chat_id is None:
                    logger.warning(
                        "%d task(s) due but no chat_id available; reminders deferred.",
                        len(due_tasks),
                    )
                else:
                    for task in due_tasks:
                        try:
                            await send_message(
                                chat_id,
                                _reminder_text(task),
                                reply_markup=build_task_keyboard(task["id"]),
                            )
                            await run_in_threadpool(_mark_reminded, task["id"])
                            logger.info("Sent reminder for task #%s.", task["id"])
                        except Exception:  # noqa: BLE001 - keep the loop alive
                            logger.exception(
                                "Failed to remind task #%s; will retry next cycle.",
                                task["id"],
                            )
        except Exception:  # noqa: BLE001 - transient DB drops must not kill the loop
            logger.exception("Reminder poll failed; retrying next cycle.")
        await asyncio.sleep(REMINDER_INTERVAL_SECONDS)