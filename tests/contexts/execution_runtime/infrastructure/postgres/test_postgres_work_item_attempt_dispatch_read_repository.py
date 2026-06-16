from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

import asyncpg
import pytest

from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_read_repository import (
    PostgresReadWorkItemAttemptDispatchRepository,
)


def _started_at() -> datetime:
    return datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)


def _row(*, dispatch_payload: object) -> dict[str, object]:
    return {
        "attempt_id": "attempt-1",
        "work_item_id": "work-1",
        "attempt_number": 1,
        "lease_token": "lease-token-1",
        "worker_ref": "worker-1",
        "dispatch_payload": dispatch_payload,
        "started_at": _started_at(),
    }


@dataclass(slots=True)
class FakeConnection:
    row: dict[str, object] | None
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.calls.append((query, args))
        return self.row


def _repository(
    connection: FakeConnection,
) -> PostgresReadWorkItemAttemptDispatchRepository:
    return PostgresReadWorkItemAttemptDispatchRepository(
        cast(asyncpg.Connection, connection),
    )


@pytest.mark.asyncio
async def test_get_dispatch_for_execution_hydrates_mapping_payload() -> None:
    repository = _repository(
        FakeConnection(row=_row(dispatch_payload={"source_unit_ref": "unit-1"}))
    )

    dispatch = await repository.get_dispatch_for_execution(attempt_id="attempt-1")

    assert dispatch is not None
    assert dict(dispatch.dispatch_payload) == {"source_unit_ref": "unit-1"}


@pytest.mark.asyncio
async def test_get_dispatch_for_execution_hydrates_json_string_payload() -> None:
    repository = _repository(
        FakeConnection(row=_row(dispatch_payload='{"source_unit_ref":"unit-1"}'))
    )

    dispatch = await repository.get_dispatch_for_execution(attempt_id="attempt-1")

    assert dispatch is not None
    assert dict(dispatch.dispatch_payload) == {"source_unit_ref": "unit-1"}


@pytest.mark.asyncio
async def test_get_dispatch_for_execution_hydrates_json_bytes_payload() -> None:
    repository = _repository(
        FakeConnection(row=_row(dispatch_payload=b'{"source_unit_ref":"unit-1"}'))
    )

    dispatch = await repository.get_dispatch_for_execution(attempt_id="attempt-1")

    assert dispatch is not None
    assert dict(dispatch.dispatch_payload) == {"source_unit_ref": "unit-1"}


@pytest.mark.asyncio
async def test_get_dispatch_for_execution_rejects_json_array_payload() -> None:
    repository = _repository(FakeConnection(row=_row(dispatch_payload='["unit-1"]')))

    with pytest.raises(
        TypeError,
        match=(
            "execution_work_item_attempt_dispatches.dispatch_payload "
            "must be JSON object Mapping; got str that decoded to list"
        ),
    ):
        await repository.get_dispatch_for_execution(attempt_id="attempt-1")


@pytest.mark.asyncio
async def test_get_dispatch_for_execution_rejects_invalid_json_payload() -> None:
    repository = _repository(FakeConnection(row=_row(dispatch_payload="not json")))

    with pytest.raises(
        ValueError,
        match=(
            "execution_work_item_attempt_dispatches.dispatch_payload "
            "must be JSON object Mapping; got invalid JSON str"
        ),
    ):
        await repository.get_dispatch_for_execution(attempt_id="attempt-1")


@pytest.mark.asyncio
async def test_get_dispatch_for_execution_returns_none_when_attempt_missing() -> None:
    repository = _repository(FakeConnection(row=None))

    dispatch = await repository.get_dispatch_for_execution(attempt_id="missing")

    assert dispatch is None
