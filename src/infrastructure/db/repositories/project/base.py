"""
Shared base for project repository modules.
"""

import uuid
from typing import Any, Optional, Union

import asyncpg
import httpx

from src.infrastructure.logging.logger import get_logger
from src.utils.encryption import encrypt_token, decrypt_token

logger = get_logger(__name__)

ProjectId = Union[str, uuid.UUID]
JsonMap = dict[str, Any]
JsonList = list[JsonMap]


def ensure_uuid(value: ProjectId) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


class ProjectRepositoryBase:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        logger.debug("ProjectRepository initialized")

    def _ensure_uuid(self, value: ProjectId) -> uuid.UUID:
        return ensure_uuid(value)

    def _encrypt_if_present(self, token: Optional[str]) -> Optional[str]:
        return encrypt_token(token) if token else None

    def _decrypt_if_present(self, encrypted: Optional[str]) -> Optional[str]:
        return decrypt_token(encrypted) if encrypted else None

    def _normalize_record(self, row: Any) -> JsonMap:
        if not row:
            empty: JsonMap = {}
            return empty

        data = dict(row)
        for key, value in list(data.items()):
            if isinstance(value, uuid.UUID):
                data[key] = str(value)
            elif hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data

    async def _get_bot_username(self, token: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{token}/getMe",
                    timeout=5.0,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return resp.json()["result"]["username"]
        except Exception as e:
            logger.warning("Failed to fetch bot username", extra={"error": str(e)})
        return None
