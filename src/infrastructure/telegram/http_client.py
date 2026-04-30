"""HTTP Telegram Bot API adapter."""

from __future__ import annotations

import httpx

from src.application.ports.telegram_port import TelegramClientPort
from src.domain.project_plane.json_types import JsonObject


class HttpTelegramClient(TelegramClientPort):
    """Small generic Telegram Bot API JSON client."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def post_json(
        self,
        bot_token: str,
        method: str,
        payload: JsonObject,
    ) -> JsonObject:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/{method}",
                json=payload,
            )

        return _telegram_response_to_json(response)


def _telegram_response_to_json(response: httpx.Response) -> JsonObject:
    try:
        body = response.json()
    except ValueError:
        return {
            "ok": response.is_success,
            "status_code": response.status_code,
        }

    if isinstance(body, dict):
        result: JsonObject = {str(key): value for key, value in body.items()}
        result.setdefault("ok", response.is_success)
        result.setdefault("status_code", response.status_code)
        return result

    return {
        "ok": response.is_success,
        "status_code": response.status_code,
    }
