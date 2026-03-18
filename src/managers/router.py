"""
Manager Bot Router.
Handles ticket notifications, claims, and replies from managers.
"""

from typing import Dict, Any
import asyncpg
import httpx

from src.core.logging import get_logger
from src.services.orchestrator import OrchestratorService
from src.services.redis_client import get_redis_client
from src.database.models import ThreadStatus

logger = get_logger(__name__)


async def process_manager_update(
    update: Dict[str, Any], 
    project_id: str, 
    orchestrator: OrchestratorService,
    bot_token: str
) -> Dict[str, bool]:
    """
    Process incoming update from a manager.
    Handles callback queries (claim ticket) and text replies.
    
    Args:
        update: Telegram Update object.
        project_id: UUID of the project.
        orchestrator: OrchestratorService instance.
        bot_token: Manager bot token for sending responses.
    
    Returns:
        Dict {"ok": True} on success.
    """
    redis = await get_redis_client()
    
    # 1. Handle Callback Query (Claim Ticket)
    if "callback_query" in update:
        cb = update["callback_query"]
        callback_id = cb["id"]
        manager_chat_id = str(cb["from"]["id"])
        data = cb.get("data", "")
        
        if data.startswith("reply:"):
            thread_id = data.split(":", 1)[1]
            key = f"awaiting_reply:{manager_chat_id}"
            await redis.setex(key, 600, thread_id)
            
            # Answer callback
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                    json={"callback_query_id": callback_id, "text": "✍️ Введите ваш ответ", "show_alert": False}
                )
            return {"ok": True}
        
        elif data.startswith("close:"):
            thread_id = data.split(":", 1)[1]
            # Update thread status to active
            try:
                await orchestrator.threads.update_status(thread_id, ThreadStatus.ACTIVE)
                # Delete awaiting_reply key if exists
                await redis.delete(f"awaiting_reply:{manager_chat_id}")
                # Answer callback
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                        json={"callback_query_id": callback_id, "text": "✅ Тикет закрыт", "show_alert": False}
                    )
            except Exception as e:
                logger.exception("Error closing ticket", extra={"thread_id": thread_id})
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                        json={"callback_query_id": callback_id, "text": f"❌ Ошибка: {str(e)}", "show_alert": True}
                    )
            return {"ok": True}
        
        return {"ok": True}

    # 2. Handle Text Message (Reply to Client)
    if "message" in update:
        msg = update["message"]
        manager_chat_id = str(msg["chat"]["id"])
        text = msg.get("text")
        
        if not text:
            return {"ok": True}
        
        key = f"awaiting_reply:{manager_chat_id}"
        thread_id = await redis.get(key)
        
        if not thread_id:
            # No active reply session
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": manager_chat_id,
                        "text": "Нет активного ожидания ответа. Пожалуйста, нажмите кнопку ✏️ Ответить под уведомлением."
                    }
                )
            return {"ok": True}
        
        try:
            # Send reply via Orchestrator
            success = await orchestrator.manager_reply(thread_id, text)
            
            if success:
                await redis.delete(key)
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": manager_chat_id, "text": "✅ Ответ успешно отправлен клиенту."}
                    )
            else:
                 async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": manager_chat_id, "text": "❌ Не удалось отправить ответ."}
                    )
                    
        except Exception as e:
            logger.exception("Error sending manager reply")
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": manager_chat_id, "text": f"❌ Ошибка: {str(e)}"}
                )
        
        return {"ok": True}
    
    return {"ok": True}
