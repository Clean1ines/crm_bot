"""Telegram transport for queue worker notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import httpx

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TelegramSendResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None


class TelegramSender:
    """Small Telegram Bot API sender wrapper."""

    async def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str | int,
        text: str,
        reply_markup: Mapping[str, object] | None = None,
    ) -> TelegramSendResult:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload: dict[str, object] = {
            "chat_id": int(chat_id),
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = dict(reply_markup)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            return TelegramSendResult(ok=True, status_code=response.status_code)

        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error sending Telegram message",
                extra={"status_code": exc.response.status_code, "error": str(exc)},
            )
            return TelegramSendResult(
                ok=False,
                status_code=exc.response.status_code,
                error=str(exc),
            )

        except httpx.RequestError as exc:
            logger.error("Request error sending Telegram message", extra={"error": str(exc)})
            return TelegramSendResult(ok=False, error=str(exc))

        except Exception as exc:
            logger.error("Unexpected error sending Telegram message", extra={"error": str(exc)})
            return TelegramSendResult(ok=False, error=str(exc))
