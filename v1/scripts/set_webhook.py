"""Register (or update) the Telegram webhook for this bot.

Usage (from the v1/ directory):
    python scripts/set_webhook.py https://myapp.example.com

The base URL gets ``/api/webhook`` appended, then Telegram's setWebhook is
called. Reads TELEGRAM_BOT_TOKEN (and optionally TELEGRAM_WEBHOOK_SECRET)
from the environment or .env.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the ``app`` package importable when running as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.telegram import set_webhook  # noqa: E402


async def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    base = sys.argv[1].strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        print(f"Error: '{sys.argv[1]}' is not an http(s) URL.")
        return 2

    data = await set_webhook(url=f"{base}/api/webhook")
    ok = bool(data.get("ok"))
    print(f"setWebhook ok={ok} description={data.get('description', '')}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))