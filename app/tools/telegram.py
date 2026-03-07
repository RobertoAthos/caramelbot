from __future__ import annotations

import os

import httpx

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def send_message(text: str, chat_id: str | None = None) -> dict:
    """Send a text message via Telegram."""
    chat_id = chat_id or TELEGRAM_CHAT_ID
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        )
        resp.raise_for_status()
        return resp.json()


async def send_document(file_path: str, caption: str = "", chat_id: str | None = None) -> dict:
    """Send a file/document via Telegram."""
    chat_id = chat_id or TELEGRAM_CHAT_ID
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{BASE_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": f},
            )
        resp.raise_for_status()
        return resp.json()


async def get_updates(offset: int | None = None, timeout: int = 30) -> list[dict]:
    """Long-poll for new Telegram messages."""
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    async with httpx.AsyncClient(timeout=timeout + 5) as client:
        resp = await client.get(f"{BASE_URL}/getUpdates", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", [])
