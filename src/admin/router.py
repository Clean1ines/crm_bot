"""
Admin Bot Router.
Dispatches incoming Telegram updates to appropriate handlers based on update type.
"""

from typing import Dict, Any, Optional, Tuple
import asyncpg
import httpx

from src.core.logging import get_logger
from src.admin.handlers import (
    handle_admin_command,
    handle_admin_step,
    handle_admin_callback,
    AdminResponse,
)
from src.admin.keyboards import make_main_menu_keyboard

logger = get_logger(__name__)


async def process_admin_update(update: Dict[str, Any], pool: asyncpg.Pool) -> Dict[str, bool]:
    """
    Main entry point for Admin Bot updates.
    Inspects the update dict and delegates to command, step, or callback handlers.
    
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
        
        # Answer callback query first to remove loading state
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_id, 
                    "text": response_text[:200] if response_text else "", 
                    "show_alert": False
                }
            )

    # 2. Handle Message
    elif "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text")
        
        if not text:
            # Ignore non-text messages (photos, etc.) in admin bot for now
            return {"ok": True}
        
        logger.debug("Admin message received", extra={"chat_id": chat_id, "text_preview": text[:50]})

        if text.startswith("/"):
            # Command
            response: AdminResponse = await handle_admin_command(text, pool)
        else:
            # Step in wizard
            response: AdminResponse = await handle_admin_step(str(chat_id), text, pool)
            
            # If no active step (returned None), show main menu
            if response is None:
                response_text = "❓ Неизвестная команда. Используйте /start."
                keyboard_dict = make_main_menu_keyboard().to_dict()
            else:
                resp_text, keyboard = response
                response_text = resp_text
                if keyboard:
                    keyboard_dict = keyboard.to_dict()

    # Send response if we have text
    if response_text and chat_id:
        payload = {
            "chat_id": chat_id,
            "text": response_text,
            "parse_mode": "Markdown"
        }
        if keyboard_dict:
            payload["reply_markup"] = keyboard_dict
            
        async with httpx.AsyncClient() as client:
            try:
                await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)
            except Exception as e:
                logger.error("Failed to send admin message", extra={"error": str(e)})

    return {"ok": True}
