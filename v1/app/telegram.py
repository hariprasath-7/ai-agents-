"""Async Telegram Bot API client built on HTTPX."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
# Telegram rejects messages longer than 4096 characters.
_MAX_MESSAGE_LEN = 4096


def _base_url() -> str:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")
    return f"{_API_BASE}/bot{token}"


async def send_message(
    chat_id: int | str,
    text: str,
    *,
    disable_web_page_preview: bool = True,
) -> dict[str, Any]:
    """Send a text message to a chat via the Telegram Bot API.

    Long messages are truncated to Telegram's 4096-character limit.
    """
    if len(text) > _MAX_MESSAGE_LEN:
        text = text[: _MAX_MESSAGE_LEN - 1] + "…"

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_web_page_preview,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{_base_url()}/sendMessage", json=payload)
        if resp.status_code == 400:
            # HTML parse failed (unmatched tags / unescaped entities); retry as plain text.
            logger.warning("sendMessage 400 with HTML parse_mode; retrying without parse_mode")
            payload.pop("parse_mode", None)
            resp = await client.post(f"{_base_url()}/sendMessage", json=payload)
        resp.raise_for_status()
        return resp.json()


async def set_webhook(
    url: str | None = None,
    *,
    secret_token: str | None = None,
) -> dict[str, Any]:
    """Register this service's webhook URL with Telegram.

    Args:
        url: Full HTTPS URL Telegram should POST updates to. Defaults to
            ``{WEBHOOK_BASE_URL}/api/webhook`` from settings.
        secret_token: Value Telegram echoes back in the
            ``X-Telegram-Bot-Api-Secret-Token`` header. Defaults to
            ``TELEGRAM_WEBHOOK_SECRET`` from settings.
    """
    if url is None:
        base = settings.webhook_base_url.rstrip("/")
        if not base:
            raise RuntimeError("WEBHOOK_BASE_URL is not configured.")
        url = f"{base}/api/webhook"

    payload: dict[str, Any] = {"url": url}
    secret = secret_token if secret_token is not None else settings.telegram_webhook_secret
    if secret:
        payload["secret_token"] = secret

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{_base_url()}/setWebhook", json=payload)
        resp.raise_for_status()
        data = resp.json()
    logger.info("setWebhook -> %s (%s)", url, data.get("description", "ok"))
    return data
