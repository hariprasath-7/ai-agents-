"""Application configuration via Pydantic settings.

All values are loaded from environment variables (or a local ``.env`` file).
Import the module-level ``settings`` singleton anywhere configuration is needed.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM / Google GenAI ---
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    agent_model: str = Field(
        default="google_genai:gemini-3.5-flash-lite",
        alias="AGENT_MODEL",
    )

    # --- Database ---
    postgres_url: str = Field(default="", alias="POSTGRES_URL")
    database_url: str = Field(default="", alias="DATABASE_URL")

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    # Shared secret Telegram echoes back in the X-Telegram-Bot-Api-Secret-Token
    # header on every webhook call; used to reject spoofed requests.
    telegram_webhook_secret: str = Field(
        default="", alias="TELEGRAM_WEBHOOK_SECRET"
    )
    # Public base URL of this service, e.g. https://myapp.example.com
    webhook_base_url: str = Field(default="", alias="WEBHOOK_BASE_URL")
    # Chat id that receives proactive due-date reminders. When empty, the bot
    # falls back to the most recent chat that messaged it.
    default_telegram_chat_id: str = Field(
        default="", alias="DEFAULT_TELEGRAM_CHAT_ID"
    )

    @property
    def resolved_google_key(self) -> str:
        """The key langchain-google-genai should use (GOOGLE_API_KEY wins)."""
        return self.google_api_key or self.gemini_api_key

    @property
    def resolved_database_url(self) -> str:
        """Preferred database connection string."""
        return self.postgres_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
