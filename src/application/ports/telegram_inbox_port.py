from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.project_plane.json_types import JsonObject
from src.domain.telegram_inbox import (
    TelegramInboxInsertResult,
    TelegramInboxRecord,
    TelegramUpdateIdentity,
)


class TelegramInboxRepositoryPort(Protocol):
    async def get_platform_telegram_bot_id(
        self,
        platform_scope: str,
    ) -> int | None: ...

    async def set_platform_telegram_bot_id(
        self,
        platform_scope: str,
        telegram_bot_id: int | None,
    ) -> None: ...

    async def insert_or_read_existing(
        self,
        *,
        identity: TelegramUpdateIdentity,
        payload: JsonObject,
        received_at: datetime,
    ) -> TelegramInboxInsertResult: ...

    async def get_by_identity(
        self,
        identity: TelegramUpdateIdentity,
    ) -> TelegramInboxRecord | None: ...

    async def claim_next(
        self,
        *,
        owner_id: str,
        owner_token: str,
        lease_expires_at: datetime,
    ) -> TelegramInboxRecord | None: ...

    async def claim_by_id(
        self,
        inbox_id: str,
        *,
        owner_id: str,
        owner_token: str,
        lease_expires_at: datetime,
    ) -> TelegramInboxRecord | None: ...

    async def renew(
        self,
        inbox_id: str,
        *,
        owner_token: str,
        lease_expires_at: datetime,
    ) -> bool: ...

    async def reclaim_expired(self, inbox_id: str) -> bool: ...

    async def reclaim_expired_batch(
        self,
        *,
        limit: int,
    ) -> tuple[TelegramInboxRecord, ...]: ...

    async def complete(
        self,
        inbox_id: str,
        *,
        owner_token: str,
    ) -> bool: ...

    async def mark_retryable_failure(
        self,
        inbox_id: str,
        *,
        owner_token: str,
        error_kind: str,
        error_message: str | None,
        next_attempt_at: datetime | None,
    ) -> bool: ...

    async def mark_terminal_failure(
        self,
        inbox_id: str,
        *,
        owner_token: str,
        error_kind: str,
        error_message: str | None,
    ) -> bool: ...
