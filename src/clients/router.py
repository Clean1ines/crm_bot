"""
Client Bot Router.
Wraps OrchestratorService to handle end-user messages.
"""

from typing import Dict, Any
import asyncpg
import httpx

from src.core.logging import get_logger
from src.services.orchestrator import OrchestratorService
from src.services.redis_client import get_redis_client

logger = get_logger(__name__)


async def process_client_update(
    update: Dict[str, Any], 
    project_id: str, 
    orchestrator: OrchestratorService,
    bot_token: str
) -> Dict[str, bool]:
    """
    Process incoming message from a client (end-user).
    Extracts text and chat_id, calls Orchestrator, and sends response.
    
    Implements idempotency via Redis: stores processed update_id to avoid duplicates.
    
    Args:
        update: Telegram Update object.
        project_id: UUID of the project.
        orchestrator: OrchestratorService instance.
        bot_token: Bot token for sending responses.
    
    Returns:
        Dict {"ok": True} on success.
    """
    # Extract update_id for idempotency check
    update_id = update.get("update_id")
    if update_id is not None:
        try:
            redis = await get_redis_client()
            key = f"processed_update:{update_id}"
            # Check if already processed
            exists = await redis.exists(key)
            if exists:
                logger.debug("Duplicate update ignored", extra={"update_id": update_id})
                return {"ok": True}
            # Mark as processed with TTL (1 hour = 3600 seconds)
            await redis.setex(key, 3600, "1")
        except Exception as e:
            # Redis unavailable – log warning and continue (risk of duplicate)
            logger.warning("Redis unavailable for idempotency check", extra={"error": str(e)})

    if "message" not in update:
        # Ignore non-message updates (edits, channel posts) for clients
        return {"ok": True}
    
    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text")
    
    if not text:
        # Ignore non-text messages
        return {"ok": True}
    
    logger.debug("Client message received", extra={"project_id": project_id, "chat_id": chat_id, "text_preview": text[:50]})
    
    try:
        # Call Orchestrator (RAG + Agent)
        response_text = await orchestrator.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text
        )
        
        # Send response
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": response_text,
                    "parse_mode": "Markdown"
                }
            )
            
    except Exception as e:
        logger.exception("Error processing client message", extra={"project_id": project_id, "chat_id": chat_id})
        # Optionally send error message to user
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": "❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже."}
            )
    
    return {"ok": True}
