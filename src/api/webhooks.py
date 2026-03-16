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

# Placeholder for future manager bot webhook
# @router.post("/manager/webhook")
# async def manager_webhook(request: Request):
#     ...
