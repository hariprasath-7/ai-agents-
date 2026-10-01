"""FastAPI application entrypoint for the Telegram AI Agent (v1).

Run locally with:  uvicorn main:app --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.routes import health, webhook
from app.scheduler import check_reminders_loop
from app.telegram import set_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup and optionally register the webhook."""
    init_db()
    logger.info("Database initialized.")

    # Auto-register the Telegram webhook when both a token and a public URL
    # are configured. Skipped silently otherwise (e.g. local dev).
    if settings.telegram_bot_token and settings.webhook_base_url:
        try:
            await set_webhook()
        except Exception:  # noqa: BLE001 - never block startup on this
            logger.exception("Failed to set Telegram webhook on startup.")

    reminder_task = asyncio.create_task(check_reminders_loop())
    logger.info("Reminder worker started.")

    yield

    reminder_task.cancel()
    try:
        await reminder_task
    except asyncio.CancelledError:
        pass
    logger.info("Reminder worker stopped.")


app = FastAPI(title="Telegram AI Agent", version="1.0.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(webhook.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Minimal index for humans hitting the service directly."""
    return {"service": "Telegram AI Agent", "version": "1.0.0"}
