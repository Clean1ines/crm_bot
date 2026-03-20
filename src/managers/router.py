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
    Handles callback queries (claim ticket, close ticket) and text replies.
    
    Args:
        update: Telegram Update object.
        project_id: UUID of the project.
        orchestrator: OrchestratorService instance.
        bot_token: Manager bot token for sending responses.
    
    Returns:
        Dict {"ok": True} on success.
    """
    redis = await get_redis_client()
    
    # 1. Handle Callback Query (Claim/Close Ticket)
    if "callback_query" in update:
        cb = update["callback_query"]
        callback_id = cb["id"]
        manager_chat_id = str(cb["from"]["id"])
        data = cb.get("data", "")
        
        if data.startswith("reply:"):
            thread_id = data.split(":", 1)[1]
            # Mark that manager is now in a reply session for this thread
            key_thread = f"awaiting_reply_thread:{thread_id}"
            key_manager = f"awaiting_reply:{manager_chat_id}"
            await redis.setex(key_thread, 600, manager_chat_id)
            await redis.setex(key_manager, 600, thread_id)
            
            # Update thread status to MANUAL
            await orchestrator.threads.update_status(thread_id, ThreadStatus.MANUAL)
            
            # Answer the callback
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                    json={"callback_query_id": callback_id, "text": "Тикет взят в работу. Теперь все сообщения клиента будут направлены вам.", "show_alert": False}
                )
            
            # Send a confirmation message with a close button
            close_markup = {
                "inline_keyboard": [[{"text": "✅ Закрыть тикет", "callback_data": f"close:{thread_id}"}]]
            }
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": manager_chat_id,
                        "text": f"Тикет {thread_id} взят в работу. Чтобы вернуть диалог AI, нажмите «Закрыть тикет».",
                        "reply_markup": close_markup
                    }
                )
            return {"ok": True}
        
        elif data.startswith("close:"):
            thread_id = data.split(":", 1)[1]
            key_thread = f"awaiting_reply_thread:{thread_id}"
            key_manager = f"awaiting_reply:{manager_chat_id}"
            
            # Clear Redis keys
            await redis.delete(key_thread)
            await redis.delete(key_manager)
            
            # Update thread status to ACTIVE
            await orchestrator.threads.update_status(thread_id, ThreadStatus.ACTIVE)
            
            # Answer callback
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                    json={"callback_query_id": callback_id, "text": "Тикет закрыт. AI снова будет отвечать клиенту.", "show_alert": False}
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
        
        # Convert thread_id from bytes to string if needed
        if isinstance(thread_id, bytes):
            thread_id = thread_id.decode()
        
        try:
            # Send reply via Orchestrator (with manager identification)
            success = await orchestrator.manager_reply(thread_id, text, manager_chat_id)
            
            if success:
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
