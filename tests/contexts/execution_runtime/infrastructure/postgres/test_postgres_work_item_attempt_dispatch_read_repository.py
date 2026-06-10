from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import asyncpg
import pytest

from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_read_repository import (
    PostgresReadWorkItemAttemptDispatchRepository,
)


class FakeConnection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.commit_count = 0
        self.rollback_count = 0

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def _started_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _dispatch_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "schedule_payload": {"provider_messages": []},
        "llm_allocation": {"slot_index": 0},
        "llm_execution_settings": {"reasoning_enabled": False},
    }


def _row() -> dict[str, object]:
    return {
        "attempt_id": "attempt-1",
        "work_item_id": "work-1",
        "attempt_number": 2,
        "lease_token": "lease-token-1",
        "worker_ref": "worker-1",
        "dispatch_payload": _dispatch_payload(),
        "started_at": _started_at(),
    }


def _repository(
    connection: FakeConnection,
) -> PostgresReadWorkItemAttemptDispatchRepository:
    return PostgresReadWorkItemAttemptDispatchRepository(
        connection=cast(asyncpg.Connection, connection),
    )


@pytest.mark.asyncio
async def test_returns_dispatch_row_with_started_at_from_attempt() -> None:
    connection = FakeConnection(row=_row())

    dispatch = await _repository(connection).get_dispatch_for_execution(
        attempt_id="attempt-1",
    )

    assert dispatch is not None
    assert dispatch.attempt_id == "attempt-1"
    assert dispatch.work_item_id == "work-1"
    assert dispatch.attempt_number == 2
    assert dispatch.lease_token == LeaseToken("lease-token-1")
    assert dispatch.worker_ref == "worker-1"
    assert dispatch.dispatch_payload == _dispatch_payload()
    assert dispatch.started_at == _started_at()
    assert connection.fetchrow_calls[0][1] == ("attempt-1",)


@pytest.mark.asyncio
async def test_returns_none_when_dispatch_not_found() -> None:
    connection = FakeConnection(row=None)

    dispatch = await _repository(connection).get_dispatch_for_execution(
        attempt_id="missing-attempt",
    )

    assert dispatch is None


@pytest.mark.asyncio
async def test_repository_does_not_commit_or_rollback() -> None:
    connection = FakeConnection(row=_row())

    await _repository(connection).get_dispatch_for_execution(attempt_id="attempt-1")

    assert connection.commit_count == 0
    assert connection.rollback_count == 0


def test_repository_has_no_llm_runtime_imports() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_read_repository.py",
    ).read_text(encoding="utf-8")

    assert "llm_runtime" not in source
