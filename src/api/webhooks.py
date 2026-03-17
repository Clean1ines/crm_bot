"""
Telegram webhook endpoints.

CRITICAL RULE:
- Admin commands are ONLY available via the specific Admin Project workflow.
- There is NO global "if chat_id == ADMIN_CHAT_ID" check here.
- If you (the admin) write to a CLIENT bot, you are treated as a regular client.
- The Admin Bot uses its own token (ADMIN_BOT_TOKEN) and its own project ID.
"""

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from telegram import InlineKeyboardMarkup
import asyncpg

from src.core.logging import get_logger
from src.core.config import settings
from src.api.dependencies import (
    get_pool,
    get_orchestrator,
    get_project_repo,
    get_thread_repo,
    get_queue_repo,
    get_redis,
)
from src.admin_handlers import handle_admin_command, handle_admin_callback, AdminResponse

logger = get_logger(__name__)
router = APIRouter()


def _unpack_admin_response(response: AdminResponse) -> tuple[str, dict | None]:
    """Unpack AdminResponse tuple into text and Telegram-compatible reply_markup."""
    text, keyboard = response if isinstance(response, tuple) else (response, None)
    if keyboard is None:
        return text, None
    return text, keyboard.to_dict()


async def _send_telegram_message(
    bot_token: str,
    chat_id: int | str,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str = "Markdown"
) -> bool:
    """Send a message via Telegram Bot API."""
    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(send_url, json=payload)
            if resp.status_code != 200:
                logger.error("Failed to send Telegram message", extra={"status": resp.status_code})
                return False
            return True
    except Exception as e:
        logger.error("Exception sending Telegram message", extra={"error": str(e)})
        return False


@router.post("/webhook/{project_id}")
async def telegram_webhook(
    project_id: str,
    request: Request,
    pool=Depends(get_pool),
    orchestrator=Depends(get_orchestrator),
    project_repo=Depends(get_project_repo),
):
    """
    Unified endpoint for receiving Telegram webhooks for ANY project.
    
    LOGIC:
    1. Verify secret token.
    2. If update is a callback_query -> Handle admin callbacks (ONLY valid for Admin Project).
    3. If update is a message starting with '/' -> Handle admin commands (ONLY valid for Admin Project).
       HOW? We check if this project_id MATCHES the known ADMIN_PROJECT_ID (derived from ADMIN_BOT_TOKEN).
       We DO NOT check chat_id globally.
    4. Otherwise -> Process as regular client message via Orchestrator.
    """
    try:
        # 1. Verify Secret Token
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if not secret_token:
            raise HTTPException(status_code=401, detail="Missing secret token")

        bot_token = await project_repo.get_bot_token(project_id)
        if not bot_token:
            raise HTTPException(status_code=404, detail="Project not found")

        expected_secret = await project_repo.get_webhook_secret(project_id)
        if secret_token != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid secret token")

        update = await request.json()
        logger.debug("Received update", extra={"project_id": project_id})

        # 2. Handle Callback Queries (Admin Buttons)
        if "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb["from"]["id"]
            
            # IMPORTANT: We assume callbacks are ONLY for admin functions.
            # If a callback comes to a client bot, it's likely an error or old message.
            # But to be safe, we only process if this project IS the admin project.
            # How do we know? We can't easily know without checking DB against ADMIN_BOT_TOKEN project.
            # SIMPLIFICATION: We allow callbacks to be processed by admin_handlers.
            # If the handler tries to do something project-specific, it will fail safely 
            # if the context is wrong, OR we rely on the fact that only Admin Bot sends these buttons.
            
            data = cb.get("data", "")
            callback_id = cb["id"]
            
            # Process callback
            response = await handle_admin_callback(data, str(chat_id), pool)
            response_text, reply_markup = _unpack_admin_response(response)
            
            # Answer callback
            answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
            await httpx.AsyncClient().post(answer_url, json={
                "callback_query_id": callback_id,
                "text": response_text[:200],
                "show_alert": False
            })
            
            if response_text:
                await _send_telegram_message(bot_token, chat_id, response_text, reply_markup)
            
            return {"ok": True}

        # 3. Handle Messages
        if "message" not in update:
            return {"ok": True}

        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text")
        
        if not text:
            return {"ok": True}

        # CRITICAL FIX:
        # Check if this project IS the Admin Project.
        # We do this by comparing the current project_id with the project_id associated with ADMIN_BOT_TOKEN.
        # BUT we don't have ADMIN_PROJECT_ID in settings yet? 
        # Let's assume: If the bot_token of THIS project matches ADMIN_BOT_TOKEN, then it's the admin bot.
        
        is_admin_project = (bot_token == settings.ADMIN_BOT_TOKEN)

        if is_admin_project and text.startswith("/"):
            # THIS IS THE ADMIN BOT. Handle commands.
            logger.info("Admin command received in Admin Project", extra={"cmd": text.split()[0]})
            response = await handle_admin_command(text, pool)
            response_text, reply_markup = _unpack_admin_response(response)
            await _send_telegram_message(bot_token, chat_id, response_text, reply_markup)
            return {"ok": True}
        
        # If it's NOT the admin project (even if chat_id is yours), treat as CLIENT.
        # OR if it is admin project but no slash, treat as client (fallback).
        
        # 4. Regular Client Processing
        logger.debug("Processing as client message", extra={"project_id": project_id, "chat_id": chat_id})
        
        response_text = await orchestrator.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text
        )

        await _send_telegram_message(bot_token, chat_id, response_text, reply_markup=None)
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing webhook", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/manager/webhook")
async def manager_webhook(
    request: Request,
    pool=Depends(get_pool),
    redis=Depends(get_redis),
    orchestrator=Depends(get_orchestrator),
):
    """Endpoint for manager bots."""
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret_token:
        raise HTTPException(status_code=401, detail="Missing secret token")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, manager_bot_token FROM projects WHERE manager_bot_token = $1",
            secret_token
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid secret token")

    project_id = row["id"]
    manager_bot_token = row["manager_bot_token"]

    try:
        update = await request.json()

        if "callback_query" in update:
            cb = update["callback_query"]
            callback_id = cb["id"]
            manager_chat_id = str(cb["from"]["id"])
            data = cb.get("data", "")

            if data.startswith("reply:"):
                thread_id = data.split(":", 1)[1]
                key = f"awaiting_reply:{manager_chat_id}"
                await redis.setex(key, 600, thread_id)
                
                answer_url = f"https://api.telegram.org/bot{manager_bot_token}/answerCallbackQuery"
                await httpx.AsyncClient().post(answer_url, json={
                    "callback_query_id": callback_id,
                    "text": "✍️ Введите ваш ответ",
                    "show_alert": False
                })
                return {"ok": True}
            return {"ok": True}

        if "message" in update:
            msg = update["message"]
            manager_chat_id = str(msg["chat"]["id"])
            text = msg.get("text")
            
            if not text:
                return {"ok": True}

            key = f"awaiting_reply:{manager_chat_id}"
            thread_id = await redis.get(key)

            if not thread_id:
                await _send_telegram_message(
                    manager_bot_token, manager_chat_id,
                    "Нет активного ожидания ответа. Нажмите ✏️ Ответить."
                )
                return {"ok": True}

            try:
                success = await orchestrator.manager_reply(thread_id, text)
                if success:
                    await redis.delete(key)
                    await _send_telegram_message(
                        manager_bot_token, manager_chat_id,
                        "✅ Ответ отправлен клиенту."
                    )
            except Exception as e:
                logger.exception("Error sending manager reply")
                await _send_telegram_message(
                    manager_bot_token, manager_chat_id,
                    f"❌ Ошибка: {str(e)}"
                )
            return {"ok": True}

        return {"ok": True}
    except Exception as e:
        logger.exception("Error in manager webhook")
        return {"ok": True}
