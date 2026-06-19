from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.infrastructure.postgres.postgres_expired_lease_recovery_repository import (
    PostgresExpiredLeaseRecoveryRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeConnection:
    queries: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.queries.append((query, args))
        return [
            {
                "work_item_id": "work-1",
                "attempt_id": "work-1:attempt:1",
            }
        ]


@pytest.mark.asyncio
async def test_reclaim_expired_leases_closes_attempt_and_returns_item_to_ready() -> (
    None
):
    connection = FakeConnection()

    result = await PostgresExpiredLeaseRecoveryRepository(connection).reclaim_expired(
        now=_now(),
        limit=25,
    )

    assert result.reclaimed_work_item_ids == ("work-1",)
    assert result.closed_attempt_ids == ("work-1:attempt:1",)
    query, args = connection.queries[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "status = 'ready'" in query
    assert "'retryable_failed'" in query
    assert "'lease_expired'" in query
    assert args == (_now(), 25)
