"""Manager Bot Router."""

from typing import cast

from src.application.dto.webhook_dto import WebhookAckDto
from src.application.ports.manager_bot_port import ManagerBotOrchestratorPort
from src.application.services.manager_bot_service import ManagerBotService
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.cache_adapter import RedisCacheAdapter
from src.infrastructure.telegram.http_client import HttpTelegramClient
from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


async def process_manager_update(
    update: dict[str, object],
    project_id: str,
    orchestrator: ConversationOrchestrator,
    bot_token: str,
) -> dict[str, bool]:
    """
    Process incoming update from a manager.
    Handles callback queries (claim ticket, close ticket) and text replies.
    """
    redis_client = await get_redis_client()
    service = ManagerBotService(
        cast(ManagerBotOrchestratorPort, orchestrator),
        RedisCacheAdapter(redis_client),
        bot_token,
        project_id,
        telegram_client=HttpTelegramClient(),
        logger=logger,
    )
    manager_user_id_value = update.get("_manager_user_id")
    manager_user_id = str(manager_user_id_value) if manager_user_id_value else None

    if "callback_query" in update:
        callback = cast(dict[str, object], update["callback_query"])
        callback_id = str(callback["id"])
        callback_from = cast(dict[str, object], callback["from"])
        manager_chat_id = str(callback_from["id"])
        data = str(callback.get("data") or "")

        if data.startswith("reply:"):
            thread_id = data.split(":", 1)[1]
            return (
                await service.claim_thread(
                    callback_id=callback_id,
                    thread_id=thread_id,
                    manager_chat_id=manager_chat_id,
                    manager_user_id=manager_user_id,
                )
            ).to_dict()

        if data.startswith("close:"):
            thread_id = data.split(":", 1)[1]
            return (
                await service.close_thread(
                    callback_id=callback_id,
                    thread_id=thread_id,
                    manager_chat_id=manager_chat_id,
                    manager_user_id=manager_user_id,
                )
            ).to_dict()

        return WebhookAckDto().to_dict()

    if "message" in update:
        message = cast(dict[str, object], update["message"])
        chat = cast(dict[str, object], message["chat"])
        manager_chat_id = str(chat["id"])
        text = str(message.get("text") or "")
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
