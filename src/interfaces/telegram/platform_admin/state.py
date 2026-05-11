"""
Redis-backed dialog state for the platform admin Telegram bot.

This module is intentionally interface-level: it knows about Telegram admin
wizard state keys and Redis, but not about project actions, token setup,
knowledge uploads, or callback routing.
"""

from __future__ import annotations

import json

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)

STATE_PREFIX = "admin_state:"
DATA_PREFIX = "admin_data:"
STATE_TTL_SECONDS = 600

STATE_IDLE = "idle"
STATE_AWAIT_PROJECT_NAME = "await_project_name"
STATE_AWAIT_CLIENT_TOKEN = "await_client_token"  # nosec B105 - dialog state name
STATE_AWAIT_MANAGER_TOKEN = "await_manager_token"  # nosec B105 - dialog state name
STATE_AWAIT_ADD_MANAGER = "await_add_manager"
STATE_DELETE_AWAIT_CONFIRM = "delete:await_confirm"
STATE_AWAIT_DETACH_CHOICE = "await_detach_choice"
STATE_AWAIT_KNOWLEDGE_FILE = "await_knowledge_file"


async def get_admin_state(chat_id: str) -> str:
    redis = await get_redis_client()
    state = await redis.get(f"{STATE_PREFIX}{chat_id}")
    if isinstance(state, bytes):
        return state.decode()
    if isinstance(state, str) and state:
        return state
    return STATE_IDLE


async def set_admin_state(chat_id: str, state: str) -> None:
    redis = await get_redis_client()
    await redis.setex(f"{STATE_PREFIX}{chat_id}", STATE_TTL_SECONDS, state)
    logger.debug("Admin state set", extra={"chat_id": chat_id, "state": state})


async def clear_admin_state(chat_id: str) -> None:
    redis = await get_redis_client()
    await redis.delete(f"{STATE_PREFIX}{chat_id}")
    await redis.delete(f"{DATA_PREFIX}{chat_id}")
    logger.debug("Admin state cleared", extra={"chat_id": chat_id})


async def get_admin_data(chat_id: str) -> dict[str, object]:
    redis = await get_redis_client()
    data = await redis.get(f"{DATA_PREFIX}{chat_id}")
    if not data:
        return {}

    if isinstance(data, bytes):
        data = data.decode()

    loaded: object = json.loads(str(data))
    if not isinstance(loaded, dict):
        logger.warning(
            "Admin state data has unexpected shape",
            extra={"chat_id": chat_id, "shape": type(loaded).__name__},
        )
        return {}

    return {str(key): value for key, value in loaded.items()}


async def set_admin_data(chat_id: str, data: dict[str, object]) -> None:
    redis = await get_redis_client()
    await redis.setex(f"{DATA_PREFIX}{chat_id}", STATE_TTL_SECONDS, json.dumps(data))
    logger.debug(
        "Admin data stored",
        extra={"chat_id": chat_id, "data_keys": list(data.keys())},
    )


def project_id_from_admin_data(data: dict[str, object]) -> str | None:
    value = data.get("project_id")
    return str(value) if value else None
