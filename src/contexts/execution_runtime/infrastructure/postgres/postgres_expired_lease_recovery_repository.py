from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class ExpiredLeaseRecoveryConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class ExpiredLeaseRecoveryResult:
    reclaimed_work_item_ids: tuple[str, ...]
    closed_attempt_ids: tuple[str, ...]

    @property
    def reclaimed_count(self) -> int:
        return len(self.reclaimed_work_item_ids)


class PostgresExpiredLeaseRecoveryRepository:
    """Atomically close abandoned attempts and release their expired work items."""

    def __init__(self, connection: ExpiredLeaseRecoveryConnectionLike) -> None:
        self._connection = connection

    async def reclaim_expired(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> ExpiredLeaseRecoveryResult:
        _require_timezone_aware(now, field_name="now")
        if not isinstance(limit, int):
            raise TypeError("limit must be int")
        if limit <= 0:
            raise ValueError("limit must be > 0")

        rows = await self._connection.fetch(
            """
            WITH expired AS (
                SELECT
                    wi.work_item_id,
                    wi.attempt_count,
                    wi.lease_token
                FROM execution_work_items AS wi
                WHERE wi.status = 'leased'
                  AND wi.lease_expires_at <= $1
                ORDER BY wi.lease_expires_at, wi.work_item_id
                FOR UPDATE SKIP LOCKED
                LIMIT $2
            ),
            closed_attempts AS (
                UPDATE execution_work_item_attempts AS attempt
                SET
                    finished_at = COALESCE(attempt.finished_at, $1),
                    outcome_status = COALESCE(
                        attempt.outcome_status,
                        'retryable_failed'
                    ),
                    error_kind = COALESCE(attempt.error_kind, 'lease_expired')
                FROM expired
                WHERE attempt.work_item_id = expired.work_item_id
                  AND attempt.attempt_number = expired.attempt_count
                RETURNING attempt.attempt_id, attempt.work_item_id
            ),
            reclaimed AS (
                UPDATE execution_work_items AS wi
                SET
                    status = 'ready',
                    leased_by = NULL,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    next_attempt_at = NULL,
                    last_error_kind = 'lease_expired',
                    retry_plan = NULL,
                    updated_at = GREATEST($1, wi.created_at)
                FROM expired
                WHERE wi.work_item_id = expired.work_item_id
                RETURNING wi.work_item_id
            )
            SELECT
                reclaimed.work_item_id,
                closed_attempts.attempt_id
            FROM reclaimed
            LEFT JOIN closed_attempts
              ON closed_attempts.work_item_id = reclaimed.work_item_id
            ORDER BY reclaimed.work_item_id
            """,
            now,
            limit,
        )

        return ExpiredLeaseRecoveryResult(
            reclaimed_work_item_ids=tuple(
                _required_text(row, "work_item_id") for row in rows
            ),
            closed_attempt_ids=tuple(
                attempt_id
                for row in rows
                if (attempt_id := _optional_text(row, "attempt_id")) is not None
            ),
        )


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text or None")
    return value


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
