"""Manager Bot Router."""


from src.application.dto.webhook_dto import WebhookAckDto
from src.application.services.manager_bot_service import ManagerBotService
from src.infrastructure.logging.logger import get_logger
from src.application.orchestration.conversation_orchestrator import ConversationOrchestrator
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


async def process_manager_update(
    update: dict[str, object],
    project_id: str,
    orchestrator: ConversationOrchestrator,
    bot_token: str
) -> dict[str, bool]:
    """
    Process incoming update from a manager.
    Handles callback queries (claim ticket, close ticket) and text replies.
    """
    redis = await get_redis_client()
    service = ManagerBotService(orchestrator, redis, bot_token, project_id)
    manager_user_id = update.get("_manager_user_id")

    if "callback_query" in update:
        callback = update["callback_query"]
        callback_id = callback["id"]
        manager_chat_id = str(callback["from"]["id"])
        data = callback.get("data", "")

        if data.startswith("reply:"):
            thread_id = data.split(":", 1)[1]
            return await service.claim_thread(
                callback_id=callback_id,
                thread_id=thread_id,
                manager_chat_id=manager_chat_id,
                manager_user_id=manager_user_id,
            ).to_dict()

        if data.startswith("close:"):
            thread_id = data.split(":", 1)[1]
            return await service.close_thread(
                callback_id=callback_id,
                thread_id=thread_id,
                manager_chat_id=manager_chat_id,
                manager_user_id=manager_user_id,
            ).to_dict()

        return WebhookAckDto().to_dict()

    if "message" in update:
        message = update["message"]
        manager_chat_id = str(message["chat"]["id"])
        text = message.get("text")
        if not text:
            return WebhookAckDto().to_dict()
        return (
            await service.reply_from_manager(
                manager_chat_id=manager_chat_id,
                text=text,
                manager_user_id=manager_user_id,
            )
        ).to_dict()

    return WebhookAckDto().to_dict()
