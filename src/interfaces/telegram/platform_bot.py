"""
Admin Bot Router.
Dispatches incoming Telegram updates to appropriate handlers based on update type.
"""

import asyncpg
import httpx
import json

from src.infrastructure.logging.logger import get_logger
from src.interfaces.telegram.platform_admin.handlers import (
    AdminResponse,
    _get_state,
    handle_admin_callback,
    handle_admin_command,
    handle_admin_step,
)
from src.interfaces.telegram.platform_admin.keyboards import make_main_menu_keyboard
from src.interfaces.telegram.platform_admin.knowledge_upload import (
    handle_knowledge_upload,
)

logger = get_logger(__name__)

STATE_AWAIT_KNOWLEDGE_FILE = "await_knowledge_file"

TelegramPayload = dict[str, object]
AdminUpdateResult = dict[str, bool]
PreparedResponse = tuple[int | None, str | None, TelegramPayload | None]


def _keyboard_to_dict(
    response: AdminResponse, *, source: str
) -> tuple[str, TelegramPayload | None]:
    response_text, keyboard = response
    if not keyboard:
        return response_text, None

    keyboard_dict = keyboard.to_dict()
    logger.debug("%s response keyboard: %s", source, json.dumps(keyboard_dict))
    return response_text, keyboard_dict


def _main_menu_response(text: str) -> tuple[str, TelegramPayload]:
    return text, make_main_menu_keyboard().to_dict()


def _extract_bot_token(update: dict[str, object]) -> str | None:
    bot_token = update.get("_bot_token")
    return str(bot_token) if bot_token else None


async def _answer_callback_query(
    bot_token: str, callback_id: str, response_text: str | None
) -> None:
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": response_text[:200] if response_text else "",
                    "show_alert": False,
                },
            )
        except Exception as exc:
            logger.error("Failed to answer callback query: %s", exc)


async def _handle_callback_query(
    callback_query: dict[str, object],
    *,
    bot_token: str,
    pool: asyncpg.Pool,
) -> PreparedResponse:
    chat_id = callback_query["from"]["id"]
    data = callback_query.get("data", "")
    callback_id = callback_query["id"]

    logger.debug("Admin callback received", extra={"chat_id": chat_id, "data": data})

    response = await handle_admin_callback(data, str(chat_id), pool)
    response_text, keyboard_dict = _keyboard_to_dict(response, source="Callback")

    await _answer_callback_query(bot_token, callback_id, response_text)
    return chat_id, response_text, keyboard_dict


async def _handle_document_message(
    chat_id: int,
    message: dict[str, object],
    pool: asyncpg.Pool,
) -> tuple[str, TelegramPayload | None]:
    state = await _get_state(str(chat_id))
    if state == STATE_AWAIT_KNOWLEDGE_FILE:
        response = await handle_knowledge_upload(str(chat_id), message, pool)
        return _keyboard_to_dict(response, source="Knowledge upload")

    return _main_menu_response("❌ Не ожидал файл. Пожалуйста, используйте меню.")


async def _handle_command_message(
    text: str, pool: asyncpg.Pool
) -> tuple[str | None, TelegramPayload | None]:
    response = await handle_admin_command(text, pool)
    if response is None:
        return None, None

    return _keyboard_to_dict(response, source="Command")


async def _handle_wizard_step_message(
    chat_id: int,
    text: str,
    pool: asyncpg.Pool,
) -> tuple[str, TelegramPayload | None]:
    response = await handle_admin_step(str(chat_id), text, pool)
    if response is None:
        return _main_menu_response("❓ Неизвестная команда. Используйте /start.")

    return _keyboard_to_dict(response, source="Step")


async def _handle_text_message(
    chat_id: int,
    text: str,
    pool: asyncpg.Pool,
) -> tuple[str | None, TelegramPayload | None]:
    logger.debug(
        "Admin message received", extra={"chat_id": chat_id, "text_preview": text[:50]}
    )

    if text.startswith("/"):
        return await _handle_command_message(text, pool)

    return await _handle_wizard_step_message(chat_id, text, pool)


async def _handle_message(
    message: dict[str, object], pool: asyncpg.Pool
) -> PreparedResponse:
    chat_id = message["chat"]["id"]
    text = message.get("text")
    document = message.get("document")

    if document:
        response_text, keyboard_dict = await _handle_document_message(
            chat_id, message, pool
        )
        return chat_id, response_text, keyboard_dict

    if text:
        response_text, keyboard_dict = await _handle_text_message(chat_id, text, pool)
        return chat_id, response_text, keyboard_dict

    return chat_id, None, None


def _build_send_message_payload(
    chat_id: int,
    response_text: str,
    keyboard_dict: TelegramPayload | None,
) -> TelegramPayload:
    payload: TelegramPayload = {
        "chat_id": chat_id,
        "text": response_text,
        "parse_mode": "Markdown",
    }

    if keyboard_dict:
        payload["reply_markup"] = keyboard_dict

    return payload


async def _send_admin_message(
    *,
    bot_token: str,
    chat_id: int,
    response_text: str,
    keyboard_dict: TelegramPayload | None,
) -> None:
    payload = _build_send_message_payload(chat_id, response_text, keyboard_dict)

    logger.debug(
        "Sending admin message to %s: payload %s",
        chat_id,
        json.dumps(payload, ensure_ascii=False)[:500],
    )

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload
            )
            if resp.status_code != 200:
                logger.error(
                    "Telegram sendMessage failed with status %s",
                    resp.status_code,
                    extra={"response_text": resp.text, "payload": payload},
                )
            else:
                logger.debug("Message sent successfully")
        except Exception as exc:
            logger.error("Exception while sending message: %s", exc, exc_info=True)


async def _dispatch_admin_update(
    update: dict[str, object],
    *,
    bot_token: str,
    pool: asyncpg.Pool,
) -> PreparedResponse:
    if "callback_query" in update:
        return await _handle_callback_query(
            update["callback_query"], bot_token=bot_token, pool=pool
        )

    if "message" in update:
        return await _handle_message(update["message"], pool)

    return None, None, None


async def process_admin_update(
    update: dict[str, object], pool: asyncpg.Pool
) -> AdminUpdateResult:
    """
    Main entry point for Admin Bot updates.
    Inspects the update dict and delegates to command, step, callback, or document handlers.
    """
    bot_token = _extract_bot_token(update)
    if not bot_token:
        logger.error("Bot token missing in admin update context")
        return {"ok": False}

    chat_id, response_text, keyboard_dict = await _dispatch_admin_update(
        update,
        bot_token=bot_token,
        pool=pool,
    )

    if response_text and chat_id:
        await _send_admin_message(
            bot_token=bot_token,
            chat_id=chat_id,
            response_text=response_text,
            keyboard_dict=keyboard_dict,
        )

    return {"ok": True}
