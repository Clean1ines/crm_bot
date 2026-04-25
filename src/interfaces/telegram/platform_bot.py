"""
Admin Bot Router.
Dispatches incoming Telegram updates to appropriate handlers based on update type.
"""

from typing import Dict, Any, Optional, Tuple
import asyncpg
import httpx
import json

from src.infrastructure.logging.logger import get_logger
from src.interfaces.telegram.platform_admin.handlers import (
    handle_admin_command,
    handle_admin_step,
    handle_admin_callback,
    AdminResponse,
    _get_state,
)
from src.interfaces.telegram.platform_admin.knowledge_upload import handle_knowledge_upload
from src.interfaces.telegram.platform_admin.keyboards import make_main_menu_keyboard

logger = get_logger(__name__)

# State constants (copied from handlers for consistency)
STATE_AWAIT_KNOWLEDGE_FILE = "await_knowledge_file"


async def process_admin_update(update: Dict[str, Any], pool: asyncpg.Pool) -> Dict[str, bool]:
    """
    Main entry point for Admin Bot updates.
    Inspects the update dict and delegates to command, step, callback, or document handlers.
    
    Args:
        update: Telegram Update object (dict).
        pool: Database connection pool.
    
    Returns:
        Dict {"ok": True} on success.
    """
    chat_id = None
    response_text: Optional[str] = None
    keyboard_dict: Optional[Dict[str, Any]] = None

    # Inject bot_token from update context (set by webhook gateway)
    bot_token = update.get("_bot_token")
    if not bot_token:
        logger.error("Bot token missing in admin update context")
        return {"ok": False}

    # 1. Handle Callback Query
    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["from"]["id"]
        data = cb.get("data", "")
        callback_id = cb["id"]
        
        logger.debug("Admin callback received", extra={"chat_id": chat_id, "data": data})
        
        response: AdminResponse = await handle_admin_callback(data, str(chat_id), pool)
        resp_text, keyboard = response
        
        response_text = resp_text
        if keyboard:
            keyboard_dict = keyboard.to_dict()
            logger.debug(f"Callback response keyboard: {json.dumps(keyboard_dict)}")
        
        # Answer callback query first to remove loading state
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                    json={
                        "callback_query_id": callback_id, 
                        "text": response_text[:200] if response_text else "", 
                        "show_alert": False
                    }
                )
            except Exception as e:
                logger.error(f"Failed to answer callback query: {e}")

    # 2. Handle Message
    elif "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text")
        document = msg.get("document")
        
        # 2a. Document upload (knowledge base)
        if document:
            state = await _get_state(str(chat_id))
            if state == STATE_AWAIT_KNOWLEDGE_FILE:
                response_text, keyboard = await handle_knowledge_upload(str(chat_id), msg, pool)
                if keyboard:
                    keyboard_dict = keyboard.to_dict()
            else:
                response_text = "❌ Не ожидал файл. Пожалуйста, используйте меню."
                keyboard_dict = make_main_menu_keyboard().to_dict()
        
        # 2b. Text message
        elif text:
            logger.debug("Admin message received", extra={"chat_id": chat_id, "text_preview": text[:50]})

            response: Optional[AdminResponse] = None
            if text.startswith("/"):
                # Command
                response = await handle_admin_command(text, pool)
                if response:
                    response_text, keyboard = response
                    if keyboard:
                        keyboard_dict = keyboard.to_dict()
                        logger.debug(f"Command response keyboard: {json.dumps(keyboard_dict)}")
            else:
                # Step in wizard
                response = await handle_admin_step(str(chat_id), text, pool)
                
                # If no active step (returned None), show main menu
                if response is None:
                    response_text = "❓ Неизвестная команда. Используйте /start."
                    keyboard_dict = make_main_menu_keyboard().to_dict()
                else:
                    resp_text, keyboard = response
                    response_text = resp_text
                    if keyboard:
                        keyboard_dict = keyboard.to_dict()
                        logger.debug(f"Step response keyboard: {json.dumps(keyboard_dict)}")
        else:
            # Ignore other non-text, non-document messages
            return {"ok": True}

    # Send response if we have text
    if response_text and chat_id:
        payload = {
            "chat_id": chat_id,
            "text": response_text,
            "parse_mode": "Markdown"
        }
        if keyboard_dict:
            payload["reply_markup"] = keyboard_dict
        
        logger.debug(f"Sending admin message to {chat_id}: payload {json.dumps(payload, ensure_ascii=False)[:500]}")
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)
                if resp.status_code != 200:
                    logger.error(
                        f"Telegram sendMessage failed with status {resp.status_code}",
                        extra={"response_text": resp.text, "payload": payload}
                    )
                else:
                    logger.debug("Message sent successfully")
            except Exception as e:
                logger.error(f"Exception while sending message: {e}", exc_info=True)

    return {"ok": True}
