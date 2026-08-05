from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

import asyncpg

from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.domain.telegram_inbox import (
    TelegramInboxInsertResult,
    TelegramInboxRecord,
    TelegramInboxStatus,
    TelegramUpdateIdentity,
    TelegramUpdateSurface,
)


class PostgresTelegramInboxRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_platform_telegram_bot_id(self, platform_scope: str) -> int | None:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT telegram_bot_id
                FROM public.platform_telegram_bot_configurations
                WHERE platform_scope = $1
                """,
                platform_scope,
            )
        return int(value) if value is not None else None

    async def set_platform_telegram_bot_id(
        self,
        platform_scope: str,
        telegram_bot_id: int | None,
    ) -> None:
        _validate_optional_bot_id(telegram_bot_id)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO public.platform_telegram_bot_configurations (
                    platform_scope,
                    telegram_bot_id,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, NOW(), NOW())
                ON CONFLICT (platform_scope) DO UPDATE
                SET telegram_bot_id = EXCLUDED.telegram_bot_id,
                    updated_at = NOW()
                """,
                platform_scope,
                telegram_bot_id,
            )

    async def insert_or_read_existing(
        self,
        *,
        identity: TelegramUpdateIdentity,
        payload: JsonObject,
        received_at: datetime,
    ) -> TelegramInboxInsertResult:
        payload_hash = _payload_hash(payload)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.telegram_inbox_updates (
                    surface,
                    project_id,
                    platform_scope,
                    telegram_bot_id,
                    telegram_update_id,
                    original_payload,
                    original_payload_hash,
                    received_at,
                    updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $8)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                identity.surface.value,
                _project_uuid(identity),
                identity.platform_scope,
                identity.telegram_bot_id,
                identity.telegram_update_id,
                _json_dumps(payload),
                payload_hash,
                received_at,
            )
            if row is not None:
                return TelegramInboxInsertResult(
                    record=_hydrate_record(row),
                    created=True,
                    duplicate=False,
                    payload_anomaly=False,
                )

            existing = await self._record_duplicate(
                conn,
                identity=identity,
                payload_hash=payload_hash,
                duplicate_at=received_at,
            )
            if existing is None:
                raise RuntimeError("telegram inbox duplicate record was not readable")
            return TelegramInboxInsertResult(
                record=existing,
                created=False,
                duplicate=True,
                payload_anomaly=existing.original_payload_hash != payload_hash,
            )

    async def get_by_identity(
        self,
        identity: TelegramUpdateIdentity,
    ) -> TelegramInboxRecord | None:
        async with self.pool.acquire() as conn:
            row = await self._fetch_by_identity(conn, identity)
        return _hydrate_record(row) if row is not None else None

    async def claim_next(
        self,
        *,
        owner_id: str,
        owner_token: str,
        lease_expires_at: datetime,
    ) -> TelegramInboxRecord | None:
        _validate_owner(owner_id, "owner_id")
        _validate_owner(owner_token, "owner_token")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'processing',
                    owned_by = $1,
                    owner_token = $2,
                    lease_expires_at = $3,
                    attempt_count = attempt_count + 1,
                    started_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    next_attempt_at = NULL,
                    last_error_kind = NULL,
                    last_error_message = NULL
                WHERE id = (
                    SELECT id
                    FROM public.telegram_inbox_updates
                    WHERE status IN ('received', 'retryable_failed')
                      AND (next_attempt_at IS NULL OR next_attempt_at <= clock_timestamp())
                      AND $3 > clock_timestamp()
                    ORDER BY
                        CASE status
                            WHEN 'retryable_failed' THEN 0
                            WHEN 'received' THEN 1
                            ELSE 2
                        END,
                        next_attempt_at NULLS FIRST,
                        received_at,
                        id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
                """,
                owner_id,
                owner_token,
                lease_expires_at,
            )
        return _hydrate_record(row) if row is not None else None

    async def claim_by_id(
        self,
        inbox_id: str,
        *,
        owner_id: str,
        owner_token: str,
        lease_expires_at: datetime,
    ) -> TelegramInboxRecord | None:
        _validate_owner(owner_id, "owner_id")
        _validate_owner(owner_token, "owner_token")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'processing',
                    owned_by = $2,
                    owner_token = $3,
                    lease_expires_at = $4,
                    attempt_count = attempt_count + 1,
                    started_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    next_attempt_at = NULL,
                    last_error_kind = NULL,
                    last_error_message = NULL
                WHERE id = $1
                  AND status IN ('received', 'retryable_failed')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= clock_timestamp())
                  AND $4 > clock_timestamp()
                RETURNING *
                """,
                inbox_id,
                owner_id,
                owner_token,
                lease_expires_at,
            )
        return _hydrate_record(row) if row is not None else None

    async def renew(
        self,
        inbox_id: str,
        *,
        owner_token: str,
        lease_expires_at: datetime,
    ) -> bool:
        _validate_owner(owner_token, "owner_token")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET lease_expires_at = $3, updated_at = clock_timestamp()
                WHERE id = $1
                  AND status = 'processing'
                  AND owner_token = $2
                  AND lease_expires_at > clock_timestamp()
                  AND $3 > clock_timestamp()
                  AND $3 > lease_expires_at
                """,
                inbox_id,
                owner_token,
                lease_expires_at,
            )
        return result == "UPDATE 1"

    async def reclaim_expired(self, inbox_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'retryable_failed',
                    owned_by = NULL,
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    last_error_kind = 'lease_expired',
                    last_error_message = NULL,
                    next_attempt_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    failed_at = clock_timestamp()
                WHERE id = $1
                  AND status = 'processing'
                  AND lease_expires_at <= clock_timestamp()
                """,
                inbox_id,
            )
        return result == "UPDATE 1"

    async def reclaim_expired_batch(
        self,
        *,
        limit: int,
    ) -> tuple[TelegramInboxRecord, ...]:
        if limit <= 0:
            return ()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'retryable_failed',
                    owned_by = NULL,
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    last_error_kind = 'lease_expired',
                    last_error_message = NULL,
                    next_attempt_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    failed_at = clock_timestamp()
                WHERE id IN (
                    SELECT id
                    FROM public.telegram_inbox_updates
                    WHERE status = 'processing'
                      AND lease_expires_at <= clock_timestamp()
                    ORDER BY lease_expires_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                )
                RETURNING *
                """,
                limit,
            )
        return tuple(_hydrate_record(row) for row in rows)

    async def complete(
        self,
        inbox_id: str,
        *,
        owner_token: str,
    ) -> bool:
        _validate_owner(owner_token, "owner_token")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'completed',
                    owned_by = NULL,
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    completed_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    next_attempt_at = NULL
                WHERE id = $1
                  AND status = 'processing'
                  AND owner_token = $2
                  AND lease_expires_at > clock_timestamp()
                """,
                inbox_id,
                owner_token,
            )
        return result == "UPDATE 1"

    async def mark_retryable_failure(
        self,
        inbox_id: str,
        *,
        owner_token: str,
        error_kind: str,
        error_message: str | None,
        next_attempt_at: datetime | None,
    ) -> bool:
        _validate_owner(owner_token, "owner_token")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'retryable_failed',
                    owned_by = NULL,
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    last_error_kind = $3,
                    last_error_message = $4,
                    next_attempt_at = $5,
                    failed_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE id = $1
                  AND status = 'processing'
                  AND owner_token = $2
                  AND lease_expires_at > clock_timestamp()
                """,
                inbox_id,
                owner_token,
                _bounded_text(error_kind, 128),
                _bounded_text(error_message, 2000),
                next_attempt_at,
            )
        return result == "UPDATE 1"

    async def mark_terminal_failure(
        self,
        inbox_id: str,
        *,
        owner_token: str,
        error_kind: str,
        error_message: str | None,
    ) -> bool:
        _validate_owner(owner_token, "owner_token")
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    status = 'terminal_failed',
                    owned_by = NULL,
                    owner_token = NULL,
                    lease_expires_at = NULL,
                    last_error_kind = $3,
                    last_error_message = $4,
                    next_attempt_at = NULL,
                    failed_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE id = $1
                  AND status = 'processing'
                  AND owner_token = $2
                  AND lease_expires_at > clock_timestamp()
                """,
                inbox_id,
                owner_token,
                _bounded_text(error_kind, 128),
                _bounded_text(error_message, 2000),
            )
        return result == "UPDATE 1"

    async def _record_duplicate(
        self,
        conn: asyncpg.Connection,
        *,
        identity: TelegramUpdateIdentity,
        payload_hash: str,
        duplicate_at: datetime,
    ) -> TelegramInboxRecord | None:
        row = await conn.fetchrow(
            """
            UPDATE public.telegram_inbox_updates
            SET
                duplicate_count = duplicate_count + 1,
                last_duplicate_at = $6,
                payload_anomaly_count = payload_anomaly_count
                    + CASE WHEN original_payload_hash <> $5 THEN 1 ELSE 0 END,
                last_payload_anomaly_at = CASE
                    WHEN original_payload_hash <> $5 THEN $6
                    ELSE last_payload_anomaly_at
                END,
                last_payload_anomaly_hash = CASE
                    WHEN original_payload_hash <> $5 THEN $5
                    ELSE last_payload_anomaly_hash
                END
            WHERE surface = $1
              AND project_id IS NOT DISTINCT FROM $2::uuid
              AND platform_scope IS NOT DISTINCT FROM $3
              AND telegram_bot_id = $4
              AND telegram_update_id = $7
            RETURNING *
            """,
            identity.surface.value,
            _project_uuid(identity),
            identity.platform_scope,
            identity.telegram_bot_id,
            payload_hash,
            duplicate_at,
            identity.telegram_update_id,
        )
        return _hydrate_record(row) if row is not None else None

    async def _fetch_by_identity(
        self,
        conn: asyncpg.Connection,
        identity: TelegramUpdateIdentity,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            SELECT *
            FROM public.telegram_inbox_updates
            WHERE surface = $1
              AND project_id IS NOT DISTINCT FROM $2::uuid
              AND platform_scope IS NOT DISTINCT FROM $3
              AND telegram_bot_id = $4
              AND telegram_update_id = $5
            """,
            identity.surface.value,
            _project_uuid(identity),
            identity.platform_scope,
            identity.telegram_bot_id,
            identity.telegram_update_id,
        )


def _hydrate_record(row: asyncpg.Record) -> TelegramInboxRecord:
    identity = TelegramUpdateIdentity(
        surface=TelegramUpdateSurface(str(row["surface"])),
        project_id=str(row["project_id"]) if row["project_id"] is not None else None,
        platform_scope=str(row["platform_scope"])
        if row["platform_scope"] is not None
        else None,
        telegram_bot_id=int(row["telegram_bot_id"]),
        telegram_update_id=int(row["telegram_update_id"]),
    )
    return TelegramInboxRecord(
        id=str(row["id"]),
        identity=identity,
        status=TelegramInboxStatus(str(row["status"])),
        original_payload=json_object_from_unknown(row["original_payload"]),
        original_payload_hash=str(row["original_payload_hash"]),
        received_at=_datetime(row["received_at"], "received_at"),
        updated_at=_datetime(row["updated_at"], "updated_at"),
        started_at=_optional_datetime(row["started_at"], "started_at"),
        completed_at=_optional_datetime(row["completed_at"], "completed_at"),
        failed_at=_optional_datetime(row["failed_at"], "failed_at"),
        owned_by=_optional_str(row["owned_by"]),
        owner_token=_optional_str(row["owner_token"]),
        lease_expires_at=_optional_datetime(
            row["lease_expires_at"], "lease_expires_at"
        ),
        attempt_count=int(row["attempt_count"]),
        last_error_kind=_optional_str(row["last_error_kind"]),
        last_error_message=_optional_str(row["last_error_message"]),
        next_attempt_at=_optional_datetime(row["next_attempt_at"], "next_attempt_at"),
        duplicate_count=int(row["duplicate_count"]),
        last_duplicate_at=_optional_datetime(
            row["last_duplicate_at"], "last_duplicate_at"
        ),
        payload_anomaly_count=int(row["payload_anomaly_count"]),
        last_payload_anomaly_at=_optional_datetime(
            row["last_payload_anomaly_at"],
            "last_payload_anomaly_at",
        ),
        last_payload_anomaly_hash=_optional_str(row["last_payload_anomaly_hash"]),
    )


def _project_uuid(identity: TelegramUpdateIdentity) -> uuid.UUID | None:
    return uuid.UUID(identity.project_id) if identity.project_id is not None else None


def _validate_optional_bot_id(value: int | None) -> None:
    if value is None:
        return
    if type(value) is not int:
        raise TypeError("telegram_bot_id must be int or None")
    if value <= 0:
        raise ValueError("telegram_bot_id must be positive when provided")


def _validate_owner(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _json_dumps(payload: JsonObject) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _payload_hash(payload: JsonObject) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _bounded_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return value[:max_length]


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    return value


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _datetime(value, field_name)
