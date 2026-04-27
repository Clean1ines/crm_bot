"""
Client Bot Router.
Wraps ConversationOrchestrator to handle end-user Telegram messages.
"""

from typing import Any, Dict

import asyncpg
import httpx

from src.application.orchestration.conversation_orchestrator import ConversationOrchestrator
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)

OK_RESPONSE: Dict[str, bool] = {"ok": True}
IDEMPOTENCY_TTL_SECONDS = 3600
CLIENT_ERROR_MESSAGE = "❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже."


def _extract_message(update: Dict[str, Any]) -> Dict[str, Any] | None:
    message = update.get("message")
    return message if isinstance(message, dict) else None


def _extract_sender(message: Dict[str, Any]) -> Dict[str, Any]:
    sender = message.get("from") or message.get("chat") or {}
    return sender if isinstance(sender, dict) else {}


def _extract_full_name(sender: Dict[str, Any]) -> str | None:
    first_name = str(sender.get("first_name") or "").strip()
    last_name = str(sender.get("last_name") or "").strip()
    return " ".join(part for part in (first_name, last_name) if part) or None


async def _is_duplicate_update(update_id: object) -> bool:
    if update_id is None:
        return False

    redis = await get_redis_client()
    key = f"processed_update:{update_id}"

    exists = await redis.exists(key)
    if exists:
        logger.debug("Duplicate update ignored", extra={"update_id": update_id})
        return True

    await redis.setex(key, IDEMPOTENCY_TTL_SECONDS, "1")
    return False


async def _skip_duplicate_update(update: Dict[str, Any]) -> bool:
    try:
        return await _is_duplicate_update(update.get("update_id"))
    except Exception as exc:
        logger.warning("Redis unavailable for idempotency check", extra={"error": str(exc)})
        return False


async def _send_telegram_message(bot_token: str, chat_id: object, text: str) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
        )


async def _send_error_message(bot_token: str, chat_id: object) -> None:
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": CLIENT_ERROR_MESSAGE,
            },
        )


async def _process_text_message(
    *,
    message: Dict[str, Any],
    project_id: str,
    orchestrator: ConversationOrchestrator,
    bot_token: str,
) -> None:
    chat_id = message["chat"]["id"]
    text = message.get("text")
    sender = _extract_sender(message)

    logger.debug(
        "Client message received",
        extra={
            "project_id": project_id,
            "chat_id": chat_id,
            "text_preview": text[:50],
        },
    )

    response_text = await orchestrator.process_message(
        project_id=project_id,
        chat_id=chat_id,
        text=text,
        username=sender.get("username"),
        full_name=_extract_full_name(sender),
        source="telegram",
    )

    if response_text:
        await _send_telegram_message(bot_token, chat_id, response_text)


async def process_client_update(
    update: Dict[str, Any],
    project_id: str,
    orchestrator: ConversationOrchestrator,
    bot_token: str,
) -> Dict[str, bool]:
    """
    Process incoming message from a client end-user.

    Keeps Telegram webhook behavior intentionally tolerant:
    duplicate, non-message, and non-text updates are acknowledged with {"ok": True}.
    """
    if await _skip_duplicate_update(update):
        return OK_RESPONSE

    message = _extract_message(update)
    if message is None or not message.get("text"):
        return OK_RESPONSE

    chat_id = message["chat"]["id"]

    try:
        await _process_text_message(
            message=message,
            project_id=project_id,
            orchestrator=orchestrator,
            bot_token=bot_token,
        )
    except Exception:
        logger.exception(
            "Error processing client message",
            extra={
                "project_id": project_id,
                "chat_id": chat_id,
            },
        )
        await _send_error_message(bot_token, chat_id)

    return OK_RESPONSE
