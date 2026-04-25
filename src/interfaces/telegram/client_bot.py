"""
Client Bot Router.
Wraps OrchestratorService to handle end-user messages.
"""

from typing import Dict, Any
import asyncpg
import httpx

from src.infrastructure.logging.logger import get_logger
from src.application.orchestration.conversation_orchestrator import ConversationOrchestrator
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


async def process_client_update(
    update: Dict[str, Any], 
    project_id: str, 
    orchestrator: ConversationOrchestrator,
    bot_token: str
) -> Dict[str, bool]:
    """
    Process incoming message from a client (end-user).
    Extracts text and chat_id, calls Orchestrator, and sends response if needed.
    
    Implements idempotency via Redis: stores processed update_id to avoid duplicates.
    
    The orchestrator may already have sent the response via the graph;
    in that case it returns an empty string, and we skip sending.
    
    Args:
        update: Telegram Update object.
        project_id: UUID of the project.
        orchestrator: ConversationOrchestrator instance.
        bot_token: Bot token for sending responses (only used for error messages).
    
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
    sender = msg.get("from") or msg.get("chat") or {}
    username = sender.get("username")
    first_name = (sender.get("first_name") or "").strip()
    last_name = (sender.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part) or None
    
    if not text:
        # Ignore non-text messages
        return {"ok": True}
    
    logger.debug("Client message received", extra={"project_id": project_id, "chat_id": chat_id, "text_preview": text[:50]})
    
    try:
        # Call Orchestrator (RAG + Agent) – it may send the response itself
        response_text = await orchestrator.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text,
            username=username,
            full_name=full_name,
            source="telegram",
        )
        
        # If orchestrator returned a non-empty string, we need to send it
        # (e.g., when graph failed to send or escalation message)
        if response_text:
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
        # Send error message to user
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": "❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже."}
            )
    
    return {"ok": True}
