from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import asyncpg
import pytest

from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_lease_repository import (
    PostgresWorkItemLeaseRepository,
)


@dataclass(slots=True)
class FakeConnection:
    work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    schedules: dict[str, Mapping[str, object]] = field(default_factory=dict)
    executed_queries: list[str] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.executed_queries.append(query)
        work_kind = str(args[0])
        now = _as_datetime(args[1])
        candidates = []
        for row in self.work_items.values():
            if row["work_kind"] != work_kind:
                continue
            if row["status"] not in {"ready", "deferred", "retryable_failed"}:
                continue
            next_attempt_at = row["next_attempt_at"]
            if next_attempt_at is not None and _as_datetime(next_attempt_at) > now:
                continue
            work_item_id = str(row["work_item_id"])
            payload = self.schedules.get(work_item_id)
            if payload is None:
                continue
            candidates.append({**row, "payload": payload})

        candidates.sort(
            key=lambda candidate: (
                candidate["next_attempt_at"] is not None,
                candidate["next_attempt_at"]
                or datetime.min.replace(tzinfo=timezone.utc),
                candidate["updated_at"],
                candidate["work_item_id"],
            ),
        )
        return candidates[0] if candidates else None

    async def execute(self, query: str, *args: object) -> str:
        self.executed_queries.append(query)
        work_item_id = str(args[0])
        row = self.work_items[work_item_id]
        row["status"] = args[1]
        row["attempt_count"] = args[2]
        row["leased_by"] = args[3]
        row["lease_token"] = args[4]
        row["lease_expires_at"] = args[5]
        row["next_attempt_at"] = None
        row["last_error_kind"] = None
        row["updated_at"] = args[6]
        return "UPDATE 1"


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _updated_at(minutes: int) -> datetime:
    return datetime(2026, 6, 10, 11, minutes, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.draft_observation_extraction")


def _other_work_kind() -> WorkKind:
    return WorkKind("other.work")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _lease_token() -> LeaseToken:
    return LeaseToken("lease-token-1")


def _row(
    *,
    work_item_id: str,
    work_kind: WorkKind | None = None,
    status: WorkItemStatus = WorkItemStatus.READY,
    attempt_count: int = 0,
    next_attempt_at: datetime | None = None,
    last_error_kind: str | None = None,
    updated_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "work_item_id": work_item_id,
        "work_kind": (work_kind or _work_kind()).value,
        "status": status.value,
        "attempt_count": attempt_count,
        "leased_by": None,
        "lease_token": None,
        "lease_expires_at": None,
        "next_attempt_at": next_attempt_at,
        "last_error_kind": last_error_kind,
        "created_at": _updated_at(0),
        "updated_at": updated_at or _updated_at(1),
    }


def _connection_with(
    *rows: dict[str, object],
    payloads: Mapping[str, Mapping[str, object]] | None = None,
) -> FakeConnection:
    connection = FakeConnection()
    for row in rows:
        work_item_id = str(row["work_item_id"])
        connection.work_items[work_item_id] = row
        connection.schedules[work_item_id] = (payloads or {}).get(
            work_item_id, {"source_unit_ref": work_item_id}
        )
    return connection


def _repository(connection: FakeConnection) -> PostgresWorkItemLeaseRepository:
    return PostgresWorkItemLeaseRepository(cast(asyncpg.Connection, connection))


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("expected datetime")
    return value


@pytest.mark.asyncio
async def test_leases_ready_due_item_and_returns_payload() -> None:
    connection = _connection_with(
        _row(work_item_id="work-1"),
        payloads={"work-1": {"source_unit_ref": "unit-1"}},
    )

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is not None
    assert leased.work_item.work_item_id == "work-1"
    assert leased.work_item.status is WorkItemStatus.LEASED
    assert leased.schedule_payload == {"source_unit_ref": "unit-1"}


@pytest.mark.asyncio
async def test_increments_attempt_count_and_writes_lease_fields() -> None:
    connection = _connection_with(_row(work_item_id="work-1", attempt_count=2))

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is not None
    assert leased.work_item.attempt_count == 3
    row = connection.work_items["work-1"]
    assert row["status"] == "leased"
    assert row["attempt_count"] == 3
    assert row["leased_by"] == "worker-1"
    assert row["lease_token"] == "lease-token-1"
    assert row["lease_expires_at"] == _lease_expires_at()


@pytest.mark.asyncio
async def test_clears_next_attempt_at_and_last_error_kind() -> None:
    connection = _connection_with(
        _row(
            work_item_id="work-1",
            status=WorkItemStatus.RETRYABLE_FAILED,
            next_attempt_at=_updated_at(30),
            last_error_kind="rate_limit",
        ),
    )

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is not None
    row = connection.work_items["work-1"]
    assert row["next_attempt_at"] is None
    assert row["last_error_kind"] is None


@pytest.mark.asyncio
async def test_does_not_lease_future_deferred_item() -> None:
    connection = _connection_with(
        _row(
            work_item_id="work-1",
            status=WorkItemStatus.DEFERRED,
            next_attempt_at=datetime(2026, 6, 10, 12, 10, tzinfo=timezone.utc),
        ),
    )

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is None
    assert connection.work_items["work-1"]["status"] == "deferred"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    (
        WorkItemStatus.COMPLETED,
        WorkItemStatus.CANCELLED,
        WorkItemStatus.TERMINAL_FAILED,
        WorkItemStatus.SPLIT_SUPERSEDED,
        WorkItemStatus.USER_ACTION_REQUIRED,
    ),
)
async def test_does_not_lease_terminal_or_non_due_statuses(
    status: WorkItemStatus,
) -> None:
    connection = _connection_with(_row(work_item_id="work-1", status=status))

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is None
    assert connection.work_items["work-1"]["status"] == status.value


@pytest.mark.asyncio
async def test_orders_due_items_deterministically() -> None:
    connection = _connection_with(
        _row(
            work_item_id="work-3",
            next_attempt_at=_updated_at(30),
            updated_at=_updated_at(3),
        ),
        _row(work_item_id="work-2", next_attempt_at=None, updated_at=_updated_at(2)),
        _row(work_item_id="work-1", next_attempt_at=None, updated_at=_updated_at(1)),
    )

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is not None
    assert leased.work_item.work_item_id == "work-1"


@pytest.mark.asyncio
async def test_filters_by_work_kind() -> None:
    connection = _connection_with(
        _row(work_item_id="other-1", work_kind=_other_work_kind()),
    )

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )

    assert leased is None


def test_sql_uses_atomic_skip_locked_due_selection() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py",
    ).read_text(encoding="utf-8")

    required = (
        "FOR UPDATE SKIP LOCKED",
        "wi.status IN ('ready', 'deferred', 'retryable_failed')",
        "wi.next_attempt_at <= $2",
        "ORDER BY",
        "LIMIT 1",
        "execution_work_items",
        "execution_work_item_schedules",
    )
    for marker in required:
        assert marker in source


def test_source_guard_forbids_workbench_capacity_llm_or_artifact_imports() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Groq",
        "qwen",
        "Prompt",
        "DraftObservation",
        "source_unit",
        "psycopg",
        "SyncConnection",
        "asyncio.run",
        "run_until_complete",
        "commit(",
        "rollback(",
    )
    for marker in forbidden:
        assert marker not in source
