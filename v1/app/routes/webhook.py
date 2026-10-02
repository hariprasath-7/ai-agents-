"""Telegram webhook endpoint.

Receives updates from Telegram, acknowledges them immediately, and processes
the agent reply in a background task so Telegram's short webhook timeout is
never exceeded.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from starlette.concurrency import run_in_threadpool

from app.agent import run_agent
from app.config import settings
from app.database import Todo, session_scope
from app.scheduler import record_active_chat
from app.telegram import answer_callback_query, edit_message_text, send_message
from app.tools import USER_TZ

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["telegram"])


def _verify_secret(header_value: str | None) -> None:
    """Reject requests whose secret header doesn't match the configured one."""
    expected = settings.telegram_webhook_secret
    if expected and header_value != expected:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")


async def _handle_message(chat_id: int, text: str) -> None:
    """Run the agent for one message and reply to the chat.

    Executed in the background; blocking agent work runs in a threadpool so it
    does not stall the event loop.
    """
    try:
        reply = await run_in_threadpool(run_agent, text)
    except Exception:  # noqa: BLE001 - surface any failure back to the user
        logger.exception("Agent failed for chat %s", chat_id)
        reply = "Sorry, something went wrong while handling your request."
    try:
        await send_message(chat_id, reply)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send Telegram reply to chat %s", chat_id)


def _parse_callback_data(data: str) -> tuple[str | None, int | None]:
    """Split callback_data into (action, task_id).

    Supported shapes: done:{id}, del:{id}, prio:{level}:{id},
    snooze:{minutes}:{id}. Returns (None, None) for anything else.
    """
    parts = data.split(":")
    try:
        if parts[0] in {"done", "del"} and len(parts) == 2:
            return parts[0], int(parts[1])
        if parts[0] in {"prio", "snooze"} and len(parts) == 3:
            return f"{parts[0]}:{parts[1]}", int(parts[2])
    except (IndexError, ValueError):
        pass
    return None, None


def _apply_callback_action(action: str, task_id: int) -> dict[str, Any]:
    """Blocking handler for one inline-keyboard click.

    Returns ``{"toast": str, "stamp": str | None}`` — the toast is shown via
    answerCallbackQuery; the stamp (when set) is appended to the original
    message and the keyboard is removed.
    """
    with session_scope() as session:
        todo = session.get(Todo, task_id)
        if todo is None:
            return {"toast": "That task no longer exists.", "stamp": None}

        if action == "done":
            todo.status = "completed"
            return {
                "toast": f"Task #{task_id} marked completed!",
                "stamp": "\n✅ <i>Completed</i>",
            }
        if action == "del":
            session.delete(todo)
            return {
                "toast": f"Task #{task_id} deleted.",
                "stamp": "\n🗑️ <i>Deleted</i>",
            }
        if action == "prio:high":
            todo.priority = "high"
            return {
                "toast": f"Task #{task_id} priority set to High!",
                "stamp": None,
            }
        if action.startswith("snooze:"):
            try:
                minutes = int(action.split(":")[1])
            except ValueError:
                return {"toast": "Invalid snooze duration.", "stamp": None}
            base = todo.due_date or datetime.now(timezone.utc)
            todo.due_date = base + timedelta(minutes=minutes)
            todo.reminded = False
            new_due = todo.due_date.astimezone(USER_TZ).strftime("%d %b %Y, %H:%M")
            return {
                "toast": f"Task #{task_id} snoozed until {new_due}.",
                "stamp": None,
            }

    return {"toast": "Unrecognized action.", "stamp": None}


async def _safe_answer(callback_query_id: str, text: str) -> None:
    """Acknowledge a callback query; never raise back into the caller."""
    try:
        await answer_callback_query(callback_query_id, text)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to answer callback query %s", callback_query_id)


async def _handle_callback_query(callback_query: dict[str, Any]) -> None:
    """Apply an inline-keyboard action and refresh the UI.

    Executed in the background; blocking DB work runs in a threadpool so it
    does not stall the event loop.
    """
    cb_id = callback_query.get("id")
    data = callback_query.get("data") or ""
    message = callback_query.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")

    action, task_id = _parse_callback_data(data)
    if cb_id is None or action is None or task_id is None:
        if cb_id is not None:
            await _safe_answer(cb_id, "Unrecognized action.")
        return

    try:
        result = await run_in_threadpool(_apply_callback_action, action, task_id)
    except Exception:  # noqa: BLE001 - surface any failure back to the user
        logger.exception("Callback action %r failed for task %s", data, task_id)
        await _safe_answer(cb_id, "Something went wrong. Please try again.")
        return

    await _safe_answer(cb_id, result["toast"])

    stamp = result["stamp"]
    if stamp and chat_id is not None and message_id is not None:
        new_text = (message.get("text") or "") + stamp
        try:
            # An empty inline_keyboard removes the now-stale action buttons.
            await edit_message_text(
                chat_id,
                message_id,
                new_text,
                reply_markup={"inline_keyboard": []},
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to edit message %s in chat %s; sending receipt instead.",
                message_id,
                chat_id,
            )
            try:
                await send_message(chat_id, result["toast"])
            except Exception:  # noqa: BLE001
                logger.exception("Failed to send callback receipt to chat %s", chat_id)


async def process_telegram_update(payload: dict[str, Any]) -> None:
    """Background worker for one Telegram update.

    Runs after the webhook has already returned 200, so Gemini parsing,
    database writes, and outbound Telegram calls here never delay the ack.
    Every exception is logged — nothing may fail silently.
    """
    try:
        # Inline keyboard button presses arrive as callback_query updates.
        callback_query = payload.get("callback_query")
        if callback_query:
            await _handle_callback_query(callback_query)
            return

        # Handle both fresh messages and edited messages.
        message = payload.get("message") or payload.get("edited_message")
        if not message:
            # Nothing actionable (e.g. a non-message update); nothing to do.
            return

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()

        if chat_id is None or not text:
            return

        # Remember this chat so the reminder worker knows where to send alerts.
        record_active_chat(chat_id)

        await _handle_message(chat_id, text)
    except Exception:  # noqa: BLE001 - background task must never crash silently
        logger.exception("Unhandled error while processing Telegram update.")


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    """Entry point for Telegram updates.

    Validates the secret token, hands the raw payload to a background worker,
    and acks with an empty 200 so Telegram's short webhook timeout is never
    exceeded — all real work (Gemini, DB, outbound sends) happens off-thread.
    """
    _verify_secret(x_telegram_bot_api_secret_token)

    payload: dict[str, Any] = await request.json()

    background_tasks.add_task(process_telegram_update, payload)
    return Response(status_code=status.HTTP_200_OK)
