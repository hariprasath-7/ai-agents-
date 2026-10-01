"""Telegram webhook endpoint.

Receives updates from Telegram, acknowledges them immediately, and processes
the agent reply in a background task so Telegram's short webhook timeout is
never exceeded.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.agent import run_agent
from app.config import settings
from app.telegram import send_message

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


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Entry point for Telegram updates.

    Validates the secret token, extracts the chat id and text from the update,
    schedules background processing, and returns immediately.
    """
    _verify_secret(x_telegram_bot_api_secret_token)

    update: dict[str, Any] = await request.json()
    # Handle both fresh messages and edited messages.
    message = update.get("message") or update.get("edited_message")
    if not message:
        # Nothing actionable (e.g. a non-message update); ack so Telegram
        # doesn't retry.
        return {"ok": True}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if chat_id is None or not text:
        return {"ok": True}

    background_tasks.add_task(_handle_message, chat_id, text)
    return {"ok": True}
