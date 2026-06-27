from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.ports.capacity_window_budget_repository_port import (
    CapacityReservation,
    CapacityWindowBudgetRepositoryPort,
    CapacityWindowBudgetSnapshot,
)


CONSERVATIVE_SEED_REQUESTS = 1
CONSERVATIVE_SEED_TOKENS = 1024


class CapacityWindowBudgetConnectionLike(Protocol):
    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...

    async def execute(self, query: str, *args: object) -> object: ...


class PostgresCapacityWindowBudgetRepository(CapacityWindowBudgetRepositoryPort):
    def __init__(self, connection: CapacityWindowBudgetConnectionLike) -> None:
        self._connection = connection

    async def get_or_seed_window(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        now: datetime,
    ) -> CapacityWindowBudgetSnapshot:
        row = await self._connection.fetchrow(
            """
            INSERT INTO capacity_window_budget_state (
                provider,
                account_ref,
                model_ref,
                remaining_minute_requests,
                remaining_minute_tokens,
                remaining_daily_requests,
                remaining_daily_tokens,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
            ON CONFLICT (provider, account_ref, model_ref) DO UPDATE SET
                updated_at = capacity_window_budget_state.updated_at
            RETURNING *
            """,
            provider,
            account_ref,
            model_ref,
            CONSERVATIVE_SEED_REQUESTS,
            CONSERVATIVE_SEED_TOKENS,
            CONSERVATIVE_SEED_REQUESTS,
            CONSERVATIVE_SEED_TOKENS,
            now,
        )
        if row is None:
            raise RuntimeError("budget seed query returned no row")
        return _snapshot_from_row(row)

    async def try_reserve(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        request_count: int,
        token_count: int,
        now: datetime,
    ) -> CapacityReservation | None:
        if request_count <= 0:
            raise ValueError("request_count must be positive")
        if token_count <= 0:
            raise ValueError("token_count must be positive")
        row = await self._connection.fetchrow(
            """
            WITH seeded AS (
                INSERT INTO capacity_window_budget_state (
                    provider,
                    account_ref,
                    model_ref,
                    remaining_minute_requests,
                    remaining_minute_tokens,
                    remaining_daily_requests,
                    remaining_daily_tokens,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, 1, 1024, 1, 1024, $6, $6)
                ON CONFLICT (provider, account_ref, model_ref) DO UPDATE SET
                    updated_at = capacity_window_budget_state.updated_at
                RETURNING *
            ),
            locked AS (
                SELECT *
                FROM capacity_window_budget_state
                WHERE provider = $1
                  AND account_ref IS NOT DISTINCT FROM $2
                  AND model_ref = $3
                FOR UPDATE
            ),
            updated AS (
                UPDATE capacity_window_budget_state AS state
                SET
                    reserved_minute_requests = state.reserved_minute_requests + $4,
                    reserved_minute_tokens = state.reserved_minute_tokens + $5,
                    reserved_daily_requests = state.reserved_daily_requests + $4,
                    reserved_daily_tokens = state.reserved_daily_tokens + $5,
                    updated_at = $6
                FROM locked
                WHERE state.provider = locked.provider
                  AND state.account_ref IS NOT DISTINCT FROM locked.account_ref
                  AND state.model_ref = locked.model_ref
                  AND (locked.frozen_until IS NULL OR locked.frozen_until <= $6)
                  AND (
                    locked.remaining_minute_requests IS NULL
                    OR locked.remaining_minute_requests - locked.reserved_minute_requests >= $4
                  )
                  AND (
                    locked.remaining_minute_tokens IS NULL
                    OR locked.remaining_minute_tokens - locked.reserved_minute_tokens >= $5
                  )
                  AND (
                    locked.remaining_daily_requests IS NULL
                    OR locked.remaining_daily_requests - locked.reserved_daily_requests >= $4
                  )
                  AND (
                    locked.remaining_daily_tokens IS NULL
                    OR locked.remaining_daily_tokens - locked.reserved_daily_tokens >= $5
                  )
                RETURNING state.provider, state.account_ref, state.model_ref
            )
            SELECT *
            FROM updated
            """,
            provider,
            account_ref,
            model_ref,
            request_count,
            token_count,
            now,
        )
        if row is None:
            return None
        return CapacityReservation(
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
            request_count=request_count,
            token_count=token_count,
            reserved_at=now,
        )

    async def release_reservation(
        self,
        *,
        reservation: CapacityReservation,
        now: datetime,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE capacity_window_budget_state
            SET
                reserved_minute_requests = GREATEST(0, reserved_minute_requests - $4),
                reserved_minute_tokens = GREATEST(0, reserved_minute_tokens - $5),
                reserved_daily_requests = GREATEST(0, reserved_daily_requests - $4),
                reserved_daily_tokens = GREATEST(0, reserved_daily_tokens - $5),
                updated_at = $6
            WHERE provider = $1
              AND account_ref IS NOT DISTINCT FROM $2
              AND model_ref = $3
            """,
            reservation.provider,
            reservation.account_ref,
            reservation.model_ref,
            reservation.request_count,
            reservation.token_count,
            now,
        )

    async def apply_capacity_observation(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        remaining_minute_requests: int | None,
        remaining_minute_tokens: int | None,
        remaining_daily_requests: int | None,
        remaining_daily_tokens: int | None,
        minute_reset_at: datetime | None,
        daily_reset_at: datetime | None,
        observed_at: datetime,
    ) -> CapacityWindowBudgetSnapshot:
        row = await self._connection.fetchrow(
            """
            INSERT INTO capacity_window_budget_state (
                provider,
                account_ref,
                model_ref,
                remaining_minute_requests,
                remaining_minute_tokens,
                remaining_daily_requests,
                remaining_daily_tokens,
                minute_reset_at,
                daily_reset_at,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
            ON CONFLICT (provider, account_ref, model_ref) DO UPDATE SET
                remaining_minute_requests = EXCLUDED.remaining_minute_requests,
                remaining_minute_tokens = EXCLUDED.remaining_minute_tokens,
                remaining_daily_requests = EXCLUDED.remaining_daily_requests,
                remaining_daily_tokens = EXCLUDED.remaining_daily_tokens,
                minute_reset_at = EXCLUDED.minute_reset_at,
                daily_reset_at = EXCLUDED.daily_reset_at,
                reserved_minute_requests = 0,
                reserved_minute_tokens = 0,
                reserved_daily_requests = 0,
                reserved_daily_tokens = 0,
                frozen_until = NULL,
                updated_at = EXCLUDED.updated_at
            RETURNING *
            """,
            provider,
            account_ref,
            model_ref,
            remaining_minute_requests,
            remaining_minute_tokens,
            remaining_daily_requests,
            remaining_daily_tokens,
            minute_reset_at,
            daily_reset_at,
            observed_at,
        )
        if row is None:
            raise RuntimeError("capacity observation query returned no row")
        return _snapshot_from_row(row)

    async def freeze_until(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        frozen_until: datetime,
        now: datetime,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO capacity_window_budget_state (
                provider,
                account_ref,
                model_ref,
                remaining_minute_requests,
                remaining_minute_tokens,
                remaining_daily_requests,
                remaining_daily_tokens,
                frozen_until,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, 1, 1024, 1, 1024, $4, $5, $5)
            ON CONFLICT (provider, account_ref, model_ref) DO UPDATE SET
                frozen_until = GREATEST(capacity_window_budget_state.frozen_until, EXCLUDED.frozen_until),
                updated_at = EXCLUDED.updated_at
            """,
            provider,
            account_ref,
            model_ref,
            frozen_until,
            now,
        )


def _snapshot_from_row(row: Mapping[str, object]) -> CapacityWindowBudgetSnapshot:
    return CapacityWindowBudgetSnapshot(
        provider=_required_str(row, "provider"),
        account_ref=_optional_str(row, "account_ref"),
        model_ref=_required_str(row, "model_ref"),
        remaining_minute_requests=_optional_int(row, "remaining_minute_requests"),
        remaining_minute_tokens=_optional_int(row, "remaining_minute_tokens"),
        remaining_daily_requests=_optional_int(row, "remaining_daily_requests"),
        remaining_daily_tokens=_optional_int(row, "remaining_daily_tokens"),
        reserved_minute_requests=_required_int(row, "reserved_minute_requests"),
        reserved_minute_tokens=_required_int(row, "reserved_minute_tokens"),
        reserved_daily_requests=_required_int(row, "reserved_daily_requests"),
        reserved_daily_tokens=_required_int(row, "reserved_daily_tokens"),
        minute_reset_at=_optional_datetime(row, "minute_reset_at"),
        daily_reset_at=_optional_datetime(row, "daily_reset_at"),
        frozen_until=_optional_datetime(row, "frozen_until"),
    )


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be null or a non-empty string")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be integer")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{key} must be null or integer")
    return value


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be null or datetime")
    return value
