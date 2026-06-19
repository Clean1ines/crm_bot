from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.infrastructure.postgres.postgres_llm_route_capacity_reservation_repository import (
    LlmRouteCapacityReservation,
    PostgresLlmRouteCapacityReservationRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeConnection:
    executed: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    rows: list[dict[str, object]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "INSERT 0 1"

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.executed.append((query, args))
        return self.rows


@pytest.mark.asyncio
async def test_lock_route_uses_transaction_advisory_lock() -> None:
    connection = FakeConnection()
    repository = PostgresLlmRouteCapacityReservationRepository(connection)

    await repository.lock_route(
        provider="groq",
        account_ref="org-1",
        model_ref="qwen/qwen3-32b",
    )

    query, args = connection.executed[0]
    assert "pg_advisory_xact_lock" in query
    assert args == ("groq|org-1|qwen/qwen3-32b",)


@pytest.mark.asyncio
async def test_active_reservations_are_aggregated_by_route() -> None:
    connection = FakeConnection(
        rows=[
            {
                "provider": "groq",
                "account_ref": "org-1",
                "model_ref": "qwen/qwen3-32b",
                "reserved_requests": 2,
                "reserved_tokens": 4200,
            }
        ]
    )
    repository = PostgresLlmRouteCapacityReservationRepository(connection)

    totals = await repository.active_totals(
        provider="groq",
        account_refs=("org-1",),
        model_ref="qwen/qwen3-32b",
        now=_now(),
    )

    assert totals[0].reserved_requests == 2
    assert totals[0].reserved_tokens == 4200


@pytest.mark.asyncio
async def test_reservation_is_persisted_and_can_be_finalized() -> None:
    connection = FakeConnection()
    repository = PostgresLlmRouteCapacityReservationRepository(connection)
    reservation = LlmRouteCapacityReservation(
        attempt_id="work-1:attempt:1",
        provider="groq",
        account_ref="org-1",
        model_ref="qwen/qwen3-32b",
        reserved_requests=1,
        reserved_tokens=3000,
        expires_at=_now() + timedelta(seconds=90),
        created_at=_now(),
    )

    await repository.reserve(reservation)
    await repository.finalize(
        attempt_id=reservation.attempt_id,
        final_status="committed",
        actual_tokens=2400,
        finalized_at=_now() + timedelta(seconds=5),
    )

    assert "INSERT INTO llm_route_capacity_reservations" in connection.executed[0][0]
    assert "UPDATE llm_route_capacity_reservations" in connection.executed[1][0]
