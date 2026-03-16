"""
Telegram webhook endpoints.
"""

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends

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
from src.admin_handlers import handle_admin_command

logger = get_logger(__name__)
router = APIRouter()

@router.post("/webhook/{project_id}")
async def telegram_webhook(
    project_id: str,
    request: Request,
    pool=Depends(get_pool),
    orchestrator=Depends(get_orchestrator),
    project_repo=Depends(get_project_repo),
):
    """
    Unified endpoint for receiving Telegram webhooks.
    Processes incoming messages and sends responses via Telegram API.
    """
    try:
        # Get the update from Telegram
        update = await request.json()
        logger.info(f"Received update from project {project_id}: {update}")

        # Check if it's a message
        if "message" not in update:
            # Ignore other update types (e.g., callback_query)
            return {"ok": True}

        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text")
        if not text:
            # Ignore non-text messages
            return {"ok": True}

        # Get bot token for this project via repository
        bot_token = await project_repo.get_bot_token(project_id)
        if not bot_token:
            logger.error(f"Bot token not found for project {project_id}")
            raise HTTPException(status_code=404, detail="Project not found or bot token missing")

        # Check if sender is admin and message is a command
        if str(chat_id) == settings.ADMIN_CHAT_ID and text.startswith("/"):
            # Handle admin command
            result = await handle_admin_command(text, pool)
            # Send response via the same bot
            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": result}
            async with httpx.AsyncClient() as client:
                await client.post(send_url, json=payload)
            return {"ok": True}

        # Otherwise, continue with normal message processing
        response_text = await orchestrator.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text
        )

        # Send the response via Telegram Bot API
        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": response_text,
            # optional: parse_mode, reply_to_message_id, etc.
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(send_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message: {resp.text}")

        return {"ok": True}

    except Exception as e:
        logger.exception("Error processing webhook")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/manager/webhook")
async def manager_webhook(
    request: Request,
    redis=Depends(get_redis),
    orchestrator=Depends(get_orchestrator),
):
    """
    Endpoint for the manager bot (the bot that sends notifications to managers).
    Handles callback queries from inline buttons and text replies from managers.
    """
    try:
        update = await request.json()
        logger.info(f"Received manager bot update: {update}")

        # 1. Handle callback query (button press)
        if "callback_query" in update:
            cb = update["callback_query"]
            callback_id = cb["id"]
            manager_chat_id = str(cb["from"]["id"])
            data = cb.get("data", "")

            # Expected format: "reply:<thread_id>"
            if data.startswith("reply:"):
                thread_id = data.split(":", 1)[1]

                # Store in Redis: awaiting_reply:<manager_chat_id> = thread_id, TTL 10 minutes
                key = f"awaiting_reply:{manager_chat_id}"
                await redis.setex(key, 600, thread_id)
                logger.info(f"Stored awaiting reply for manager {manager_chat_id}, thread {thread_id}")

                # Answer the callback to remove the loading indicator
                answer_url = f"https://api.telegram.org/bot{settings.MANAGER_BOT_TOKEN}/answerCallbackQuery"
                payload = {
                    "callback_query_id": callback_id,
                    "text": "✍️ Введите ваш ответ",
                    "show_alert": False
                }
                async with httpx.AsyncClient() as client:
                    await client.post(answer_url, json=payload)

                return {"ok": True}
            else:
                logger.warning(f"Unknown callback data: {data}")
                return {"ok": True}

        # 2. Handle text messages (manager's reply)
        if "message" in update:
            msg = update["message"]
            manager_chat_id = str(msg["chat"]["id"])
            text = msg.get("text")
            if not text:
                return {"ok": True}

            # Check if we are expecting a reply from this manager
            key = f"awaiting_reply:{manager_chat_id}"
            thread_id = await redis.get(key)

            if not thread_id:
                # No pending reply, send instructions
                send_url = f"https://api.telegram.org/bot{settings.MANAGER_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": manager_chat_id,
                    "text": "Нет активного ожидания ответа. Пожалуйста, нажмите кнопку ✏️ Ответить под уведомлением."
                }
                async with httpx.AsyncClient() as client:
                    await client.post(send_url, json=payload)
                return {"ok": True}

            try:
                # Call orchestrator to send the reply to the client
                success = await orchestrator.manager_reply(thread_id, text)

                if success:
                    # Clear the Redis key
                    await redis.delete(key)

                    # Notify manager that reply was sent
                    send_url = f"https://api.telegram.org/bot{settings.MANAGER_BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": manager_chat_id,
                        "text": "✅ Ответ успешно отправлен клиенту."
                    }
                    async with httpx.AsyncClient() as client:
                        await client.post(send_url, json=payload)
                else:
                    # Should not happen because manager_reply raises exceptions on failure
                    pass
            except Exception as e:
                logger.exception(f"Error sending manager reply for thread {thread_id}")
                # Notify manager of error
                send_url = f"https://api.telegram.org/bot{settings.MANAGER_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": manager_chat_id,
                    "text": f"❌ Ошибка при отправке ответа: {str(e)}"
                }
                async with httpx.AsyncClient() as client:
                    await client.post(send_url, json=payload)

            return {"ok": True}

        # Ignore other update types
        return {"ok": True}

    except Exception as e:
        logger.exception("Error processing manager webhook")
        # We still return 200 to Telegram to avoid resending
        return {"ok": True}
