from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class LlmRouteCapacityReservationConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class LlmRouteCapacityReservation:
    attempt_id: str
    provider: str
    account_ref: str
    model_ref: str
    reserved_requests: int
    reserved_tokens: int
    expires_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name, value in (
            ("attempt_id", self.attempt_id),
            ("provider", self.provider),
            ("account_ref", self.account_ref),
            ("model_ref", self.model_ref),
        ):
            _require_non_empty_text(value, field_name=field_name)
        _require_positive_int(
            self.reserved_requests,
            field_name="reserved_requests",
        )
        _require_positive_int(
            self.reserved_tokens,
            field_name="reserved_tokens",
        )
        _require_timezone_aware(self.expires_at, field_name="expires_at")
        _require_timezone_aware(self.created_at, field_name="created_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")


@dataclass(frozen=True, slots=True)
class LlmRouteCapacityReservationTotal:
    provider: str
    account_ref: str
    model_ref: str
    reserved_requests: int
    reserved_tokens: int


class PostgresLlmRouteCapacityReservationRepository:
    def __init__(
        self,
        connection: LlmRouteCapacityReservationConnectionLike,
    ) -> None:
        self._connection = connection

    async def lock_route(
        self,
        *,
        provider: str,
        account_ref: str,
        model_ref: str,
    ) -> None:
        route_key = _route_key(
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
        )
        await self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            route_key,
        )

    async def active_totals(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
        now: datetime,
    ) -> tuple[LlmRouteCapacityReservationTotal, ...]:
        _require_non_empty_text(provider, field_name="provider")
        _require_non_empty_text(model_ref, field_name="model_ref")
        _require_timezone_aware(now, field_name="now")
        if not account_refs:
            return ()

        rows = await self._connection.fetch(
            """
            SELECT
                provider,
                account_ref,
                model_ref,
                COUNT(*)::integer AS reserved_requests,
                COALESCE(SUM(reserved_tokens), 0)::integer AS reserved_tokens
            FROM llm_route_capacity_reservations
            WHERE provider = $1
              AND account_ref = ANY($2::text[])
              AND model_ref = $3
              AND status = 'active'
              AND expires_at > $4
            GROUP BY provider, account_ref, model_ref
            """,
            provider,
            list(account_refs),
            model_ref,
            now,
        )
        return tuple(
            LlmRouteCapacityReservationTotal(
                provider=_row_text(row, "provider"),
                account_ref=_row_text(row, "account_ref"),
                model_ref=_row_text(row, "model_ref"),
                reserved_requests=_row_non_negative_int(row, "reserved_requests"),
                reserved_tokens=_row_non_negative_int(row, "reserved_tokens"),
            )
            for row in rows
        )

    async def reserve(self, reservation: LlmRouteCapacityReservation) -> None:
        await self._connection.execute(
            """
            INSERT INTO llm_route_capacity_reservations (
                attempt_id,
                provider,
                account_ref,
                model_ref,
                reserved_requests,
                reserved_tokens,
                status,
                expires_at,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8)
            ON CONFLICT (attempt_id) DO NOTHING
            """,
            reservation.attempt_id,
            reservation.provider,
            reservation.account_ref,
            reservation.model_ref,
            reservation.reserved_requests,
            reservation.reserved_tokens,
            reservation.expires_at,
            reservation.created_at,
        )

    async def finalize(
        self,
        *,
        attempt_id: str,
        final_status: str,
        actual_tokens: int | None,
        finalized_at: datetime,
    ) -> None:
        _require_non_empty_text(attempt_id, field_name="attempt_id")
        if final_status not in {"committed", "released"}:
            raise ValueError("final_status must be committed or released")
        if actual_tokens is not None and actual_tokens < 0:
            raise ValueError("actual_tokens must be >= 0 when provided")
        _require_timezone_aware(finalized_at, field_name="finalized_at")

        await self._connection.execute(
            """
            UPDATE llm_route_capacity_reservations
            SET
                status = $2,
                actual_tokens = $3,
                finalized_at = $4
            WHERE attempt_id = $1
              AND status = 'active'
            """,
            attempt_id,
            final_status,
            actual_tokens,
            finalized_at,
        )


def actual_tokens_from_capacity_observation(
    observation: Mapping[str, object] | None,
) -> int | None:
    if observation is None:
        return None
    value = observation.get("actual_total_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _route_key(*, provider: str, account_ref: str, model_ref: str) -> str:
    for field_name, value in (
        ("provider", provider),
        ("account_ref", account_ref),
        ("model_ref", model_ref),
    ):
        _require_non_empty_text(value, field_name=field_name)
    return f"{provider}|{account_ref}|{model_ref}"


def _row_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _row_non_negative_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be non-negative int")
    return value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_positive_int(value: int, *, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
