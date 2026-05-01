"""
Shared base for project repository modules.
"""

import uuid
from dataclasses import dataclass
from time import monotonic
from typing import ClassVar, Protocol, TypeVar
from collections.abc import Mapping

import asyncpg
import httpx

from src.domain.control_plane.project_views import ProjectRuntimeSettingsView
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.utils.encryption import encrypt_token, decrypt_token

logger = get_logger(__name__)

ProjectId = str | uuid.UUID
JsonMap = dict[str, object]
JsonList = list[JsonMap]


class _ExpiringEntry(Protocol):
    expires_at: float


_CacheEntryT = TypeVar("_CacheEntryT", bound=_ExpiringEntry)


@dataclass(slots=True)
class _OptionalTextCacheEntry:
    value: str | None
    expires_at: float


@dataclass(slots=True)
class _ProjectSettingsCacheEntry:
    value: ProjectRuntimeSettingsView
    expires_at: float


def ensure_uuid(value: ProjectId) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


class ProjectRepositoryBase:
    _bot_token_cache: ClassVar[dict[str, _OptionalTextCacheEntry]] = {}
    _manager_bot_token_cache: ClassVar[dict[str, _OptionalTextCacheEntry]] = {}
    _webhook_secret_cache: ClassVar[dict[str, _OptionalTextCacheEntry]] = {}
    _manager_webhook_secret_cache: ClassVar[dict[str, _OptionalTextCacheEntry]] = {}
    _project_settings_cache: ClassVar[dict[str, _ProjectSettingsCacheEntry]] = {}

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        logger.debug("ProjectRepository initialized")

    def _ensure_uuid(self, value: ProjectId) -> uuid.UUID:
        return ensure_uuid(value)

    def _encrypt_if_present(self, token: str | None) -> str | None:
        return encrypt_token(token) if token else None

    def _decrypt_if_present(self, encrypted: str | None) -> str | None:
        return decrypt_token(encrypted) if encrypted else None

    def _normalize_record(self, row: object) -> JsonMap:
        if not row:
            empty: JsonMap = {}
            return empty

        if isinstance(row, Mapping):
            data = {str(key): value for key, value in row.items()}
        elif hasattr(row, "items"):
            row_items = row.items()
            data = {str(key): value for key, value in row_items}
        else:
            return {}

        for key, value in list(data.items()):
            if isinstance(value, uuid.UUID):
                data[key] = str(value)
            elif hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data

    def _cache_ttl_seconds(self) -> float:
        return settings.PROJECT_REPOSITORY_CACHE_TTL_SECONDS

    def _cache_max_entries(self) -> int:
        return settings.PROJECT_REPOSITORY_CACHE_MAX_ENTRIES

    def _is_cache_enabled(self) -> bool:
        return self._cache_ttl_seconds() > 0.0

    def _canonical_project_cache_key(self, project_id: ProjectId) -> str:
        return str(self._ensure_uuid(project_id))

    def _prune_cache(self, cache: dict[str, _CacheEntryT]) -> None:
        if len(cache) < self._cache_max_entries():
            return

        now = monotonic()
        expired_keys = [key for key, entry in cache.items() if entry.expires_at <= now]
        for key in expired_keys:
            cache.pop(key, None)

        if len(cache) < self._cache_max_entries():
            return

        oldest_key = min(cache.items(), key=lambda item: item[1].expires_at)[0]
        cache.pop(oldest_key, None)

    def _get_optional_text_cache_entry(
        self,
        cache: dict[str, _OptionalTextCacheEntry],
        cache_key: str,
    ) -> tuple[str | None, bool]:
        if not self._is_cache_enabled():
            return None, False

        entry = cache.get(cache_key)
        if entry is None:
            return None, False

        if entry.expires_at <= monotonic():
            cache.pop(cache_key, None)
            return None, False

        return entry.value, True

    def _set_optional_text_cache_entry(
        self,
        cache: dict[str, _OptionalTextCacheEntry],
        cache_key: str,
        value: str | None,
    ) -> None:
        if not self._is_cache_enabled():
            return

        self._prune_cache(cache)
        cache[cache_key] = _OptionalTextCacheEntry(
            value=value,
            expires_at=monotonic() + self._cache_ttl_seconds(),
        )

    def _get_project_settings_cache_entry(
        self,
        cache_key: str,
    ) -> ProjectRuntimeSettingsView | None:
        if not self._is_cache_enabled():
            return None

        entry = self._project_settings_cache.get(cache_key)
        if entry is None:
            return None

        if entry.expires_at <= monotonic():
            self._project_settings_cache.pop(cache_key, None)
            return None

        return entry.value

    def _set_project_settings_cache_entry(
        self,
        cache_key: str,
        value: ProjectRuntimeSettingsView,
    ) -> None:
        if not self._is_cache_enabled():
            return

        self._prune_cache(self._project_settings_cache)
        self._project_settings_cache[cache_key] = _ProjectSettingsCacheEntry(
            value=value,
            expires_at=monotonic() + self._cache_ttl_seconds(),
        )

    def _invalidate_project_runtime_cache(self, project_id: ProjectId) -> None:
        cache_key = self._canonical_project_cache_key(project_id)
        self._bot_token_cache.pop(cache_key, None)
        self._manager_bot_token_cache.pop(cache_key, None)
        self._webhook_secret_cache.pop(cache_key, None)
        self._manager_webhook_secret_cache.pop(cache_key, None)
        self._project_settings_cache.pop(cache_key, None)

    async def _get_bot_username(self, token: str) -> str | None:
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
