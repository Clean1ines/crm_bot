from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.domain.project_plane.json_types import JsonObject


class TelegramUpdateSurface(StrEnum):
    CLIENT = "client"
    MANAGER = "manager"
    PLATFORM_ADMIN = "platform_admin"


class TelegramInboxStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.TERMINAL_FAILED}


@dataclass(frozen=True, slots=True)
class TelegramUpdateIdentity:
    surface: TelegramUpdateSurface
    project_id: str | None
    platform_scope: str | None
    telegram_bot_id: int
    telegram_update_id: int

    def __post_init__(self) -> None:
        surface = TelegramUpdateSurface(self.surface)
        bot_id = _positive_int(self.telegram_bot_id, "telegram_bot_id")
        update_id = _non_negative_int(
            self.telegram_update_id,
            "telegram_update_id",
        )

        if surface in {TelegramUpdateSurface.CLIENT, TelegramUpdateSurface.MANAGER}:
            if self.project_id is None:
                raise ValueError("project bot identity requires project_id")
            if self.platform_scope is not None:
                raise ValueError("project bot identity forbids platform_scope")
            project_id = str(uuid.UUID(str(self.project_id)))
            platform_scope = None
        else:
            if self.project_id is not None:
                raise ValueError("platform bot identity forbids project_id")
            if self.platform_scope is None:
                raise ValueError("platform bot identity requires platform_scope")
            platform_scope = str(self.platform_scope).strip()
            if not platform_scope:
                raise ValueError("platform_scope must be non-empty")
            project_id = None

        object.__setattr__(self, "surface", surface)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "platform_scope", platform_scope)
        object.__setattr__(self, "telegram_bot_id", bot_id)
        object.__setattr__(self, "telegram_update_id", update_id)

    @classmethod
    def for_project_bot(
        cls,
        *,
        surface: TelegramUpdateSurface,
        project_id: str | uuid.UUID,
        telegram_bot_id: int,
        telegram_update_id: int,
    ) -> TelegramUpdateIdentity:
        if surface not in {TelegramUpdateSurface.CLIENT, TelegramUpdateSurface.MANAGER}:
            raise ValueError("project bot identity requires client or manager surface")
        return cls(
            surface=surface,
            project_id=str(uuid.UUID(str(project_id))),
            platform_scope=None,
            telegram_bot_id=_positive_int(telegram_bot_id, "telegram_bot_id"),
            telegram_update_id=_non_negative_int(
                telegram_update_id,
                "telegram_update_id",
            ),
        )

    @classmethod
    def for_platform_bot(
        cls,
        *,
        platform_scope: str,
        telegram_bot_id: int,
        telegram_update_id: int,
    ) -> TelegramUpdateIdentity:
        scope = platform_scope.strip()
        if not scope:
            raise ValueError("platform_scope must be non-empty")
        return cls(
            surface=TelegramUpdateSurface.PLATFORM_ADMIN,
            project_id=None,
            platform_scope=scope,
            telegram_bot_id=_positive_int(telegram_bot_id, "telegram_bot_id"),
            telegram_update_id=_non_negative_int(
                telegram_update_id,
                "telegram_update_id",
            ),
        )


@dataclass(frozen=True, slots=True)
class TelegramInboxRecord:
    id: str
    identity: TelegramUpdateIdentity
    status: TelegramInboxStatus
    original_payload: JsonObject
    original_payload_hash: str
    received_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    owned_by: str | None = None
    owner_token: str | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    last_error_kind: str | None = None
    last_error_message: str | None = None
    next_attempt_at: datetime | None = None
    duplicate_count: int = 0
    last_duplicate_at: datetime | None = None
    payload_anomaly_count: int = 0
    last_payload_anomaly_at: datetime | None = None
    last_payload_anomaly_hash: str | None = None


@dataclass(frozen=True, slots=True)
class TelegramInboxInsertResult:
    record: TelegramInboxRecord
    created: bool
    duplicate: bool
    payload_anomaly: bool


def _positive_int(value: int, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _non_negative_int(value: int, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value
