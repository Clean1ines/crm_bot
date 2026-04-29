"""Manager Bot Router."""

from collections.abc import Awaitable
import inspect
from typing import cast

import httpx
import redis.asyncio as redis

from src.application.dto.webhook_dto import WebhookAckDto
from src.application.ports.cache_port import CachePort
from src.application.ports.manager_bot_port import ManagerBotOrchestratorPort
from src.application.ports.telegram_port import TelegramClientPort
from src.application.services.manager_bot_service import ManagerBotService
from src.domain.project_plane.json_types import JsonObject
from src.infrastructure.logging.logger import get_logger
from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


class _HttpTelegramClient(TelegramClientPort):
    async def post_json(
        self,
        bot_token: str,
        method: str,
        payload: JsonObject,
    ) -> JsonObject:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/{method}",
                json=payload,
            )

        try:
            body = response.json()
        except ValueError:
            return {"ok": response.is_success, "status_code": response.status_code}

        if isinstance(body, dict):
            return {str(key): value for key, value in body.items()}

        return {"ok": response.is_success, "status_code": response.status_code}


class _RedisCacheAdapter(CachePort):
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def _resolve_int(self, value: Awaitable[object] | object) -> int:
        if inspect.isawaitable(value):
            resolved = await cast(Awaitable[object], value)
        else:
            resolved = value

        if isinstance(resolved, bool):
            return int(resolved)
        if isinstance(resolved, int):
            return resolved
        if isinstance(resolved, float):
            return int(resolved)
        if isinstance(resolved, str):
            return int(resolved)
        raise TypeError(f"Unexpected Redis integer response type: {type(resolved)!r}")

    async def get(self, key: str) -> str | bytes | None:
        value = await self._client.get(key)
        if isinstance(value, str | bytes):
            return value
        return None

    async def expire(self, key: str, seconds: int) -> bool:
        return bool(await self._client.expire(key, seconds))

    async def exists(self, key: str) -> int:
        return int(await self._client.exists(key))

    async def sadd(self, key: str, value: str) -> int:
        return await self._resolve_int(self._client.sadd(key, value))

    async def set(self, key: str, value: str, ex: int | None = None) -> bool | None:
        result = await self._client.set(key, value, ex=ex)
        return bool(result) if result is not None else None

    async def setex(self, key: str, seconds: int, value: str) -> bool | None:
        result = await self._client.setex(key, seconds, value)
        return bool(result) if result is not None else None

    async def srem(self, key: str, value: str) -> int:
        return await self._resolve_int(self._client.srem(key, value))

    async def delete(self, key: str) -> int:
        return int(await self._client.delete(key))


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
        _RedisCacheAdapter(redis_client),
        bot_token,
        project_id,
        telegram_client=_HttpTelegramClient(),
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
