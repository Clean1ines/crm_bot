from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_lease_repository import (
    PostgresWorkItemLeaseRepository,
    _hydrate_schedule_payload,
)

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import asyncpg

from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


@dataclass(slots=True)
class FakeConnection:
    work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    schedules: dict[str, Mapping[str, object]] = field(default_factory=dict)
    executed_queries: list[str] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        self.executed_queries.append(query)
        work_kind = str(args[0])
        now = _as_datetime(args[1])
        limit = int(args[2])
        candidates = self._due_candidates(work_kind=work_kind, now=now)
        return candidates[:limit]

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.executed_queries.append(query)
        work_kind = str(args[0])
        now = _as_datetime(args[1])
        candidates = self._due_candidates(work_kind=work_kind, now=now)
        return candidates[0] if candidates else None

    def _due_candidates(
        self,
        *,
        work_kind: str,
        now: datetime,
    ) -> list[Mapping[str, object]]:
        candidates: list[Mapping[str, object]] = []
        for row in self.work_items.values():
            if row["work_kind"] != work_kind:
                continue
            if row["status"] not in {"ready", "retryable_failed"}:
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
                _status_priority(str(candidate["status"])),
                candidate["next_attempt_at"] is not None,
                candidate["next_attempt_at"]
                or datetime.min.replace(tzinfo=timezone.utc),
                candidate["updated_at"],
                candidate["work_item_id"],
            ),
        )
        return candidates

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
        requested_updated_at = _as_datetime(args[6])
        created_at = _as_datetime(row["created_at"])
        row["updated_at"] = max(requested_updated_at, created_at)
        return "UPDATE 1"


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _updated_at(minutes: int) -> datetime:
    return datetime(2026, 6, 10, 11, minutes, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


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


def _status_priority(status: str) -> int:
    priority_by_status = {
        WorkItemStatus.RETRYABLE_FAILED.value: 0,
        WorkItemStatus.READY.value: 1,
    }
    return priority_by_status.get(status, 2)


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("expected datetime")
    return value


@pytest.mark.asyncio
async def test_peek_due_work_items_prioritizes_retryable_failed_then_ready_and_ignores_deferred() -> (
    None
):
    due_at = _now() - timedelta(seconds=1)
    connection = _connection_with(
        _row(
            work_item_id="work-ready",
            status=WorkItemStatus.READY,
            next_attempt_at=None,
            updated_at=_updated_at(1),
        ),
        _row(
            work_item_id="work-deferred",
            status=WorkItemStatus.DEFERRED,
            next_attempt_at=due_at,
            updated_at=_updated_at(2),
        ),
        _row(
            work_item_id="work-retry",
            status=WorkItemStatus.RETRYABLE_FAILED,
            next_attempt_at=due_at,
            last_error_kind="rate_limit",
            updated_at=_updated_at(3),
        ),
    )

    records = await _repository(connection).peek_due_work_items(
        work_kind=_work_kind(),
        requested_items=3,
        now=_now(),
    )

    assert tuple(record.work_item.work_item_id for record in records) == (
        "work-retry",
        "work-ready",
    )


@pytest.mark.asyncio
async def test_lease_due_work_item_prioritizes_retryable_failed_then_ready_and_ignores_deferred() -> (
    None
):
    due_at = _now() - timedelta(seconds=1)
    connection = _connection_with(
        _row(
            work_item_id="work-ready",
            status=WorkItemStatus.READY,
            next_attempt_at=None,
            updated_at=_updated_at(1),
        ),
        _row(
            work_item_id="work-deferred",
            status=WorkItemStatus.DEFERRED,
            next_attempt_at=due_at,
            updated_at=_updated_at(2),
        ),
        _row(
            work_item_id="work-retry",
            status=WorkItemStatus.RETRYABLE_FAILED,
            next_attempt_at=due_at,
            last_error_kind="rate_limit",
            updated_at=_updated_at(3),
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
    assert leased.work_item.work_item_id == "work-retry"


@pytest.mark.asyncio
async def test_peek_due_work_items_excludes_future_retryable_failed() -> None:
    connection = _connection_with(
        _row(
            work_item_id="work-retry-future",
            status=WorkItemStatus.RETRYABLE_FAILED,
            next_attempt_at=_now() + timedelta(minutes=1),
            last_error_kind="rate_limit",
        ),
        _row(
            work_item_id="work-ready",
            status=WorkItemStatus.READY,
            next_attempt_at=None,
        ),
    )

    records = await _repository(connection).peek_due_work_items(
        work_kind=_work_kind(),
        requested_items=3,
        now=_now(),
    )

    assert tuple(record.work_item.work_item_id for record in records) == ("work-ready",)


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
async def test_lease_update_never_writes_updated_at_before_created_at() -> None:
    created_at = datetime(2026, 6, 10, 12, 1, tzinfo=timezone.utc)
    stale_now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    connection = _connection_with(
        {
            **_row(work_item_id="work-1"),
            "created_at": created_at,
            "updated_at": stale_now,
        },
    )

    leased = await _repository(connection).lease_due_work_item(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc),
        now=stale_now,
    )

    assert leased is not None
    assert connection.work_items["work-1"]["updated_at"] == created_at

    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py",
    ).read_text(encoding="utf-8")
    assert "updated_at = GREATEST($7, created_at)" in source


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
        "wi.status IN ('ready', 'retryable_failed')",
        "wi.next_attempt_at <= $2",
        "ORDER BY",
        "CASE wi.status",
        "WHEN 'retryable_failed' THEN 0",
        "WHEN 'ready' THEN 1",
        "LIMIT 1",
        "execution_work_items",
        "execution_work_item_schedules",
    )
    for marker in required:
        assert marker in source
    assert source.count("CASE wi.status") == 2


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


def _json_payload_hydration_now() -> datetime:
    return datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)


def test_hydrate_schedule_payload_accepts_mapping() -> None:
    payload = _hydrate_schedule_payload({"source_unit_ref": "unit-1"})

    assert dict(payload) == {"source_unit_ref": "unit-1"}


def test_hydrate_schedule_payload_accepts_json_string_object() -> None:
    payload = _hydrate_schedule_payload('{"source_unit_ref":"unit-1"}')

    assert dict(payload) == {"source_unit_ref": "unit-1"}


def test_hydrate_schedule_payload_accepts_json_bytes_object() -> None:
    payload = _hydrate_schedule_payload(b'{"source_unit_ref":"unit-1"}')

    assert dict(payload) == {"source_unit_ref": "unit-1"}


def test_hydrate_schedule_payload_rejects_json_array() -> None:
    with pytest.raises(
        TypeError,
        match=(
            "execution_work_item_schedules.payload must be JSON object Mapping; "
            "got str that decoded to list"
        ),
    ):
        _hydrate_schedule_payload('["unit-1"]')


@dataclass(slots=True)
class FakeLeaseConnection:
    row: dict[str, object] | None
    executed: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        del query, args
        return self.row

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_lease_due_work_item_accepts_json_string_schedule_payload() -> None:
    now = _json_payload_hydration_now()
    connection = FakeLeaseConnection(
        row={
            "work_item_id": "work-1",
            "work_kind": "claim_builder_section_work",
            "status": "ready",
            "attempt_count": 0,
            "leased_by": None,
            "lease_token": None,
            "lease_expires_at": None,
            "next_attempt_at": None,
            "last_error_kind": None,
            "created_at": now,
            "updated_at": now,
            "payload": '{"source_unit_ref":"unit-1"}',
        },
    )
    repository = PostgresWorkItemLeaseRepository(connection)

    leased = await repository.lease_due_work_item(
        work_kind=WorkKind("claim_builder_section_work"),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-token-1"),
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )

    assert leased is not None
    assert dict(leased.schedule_payload) == {"source_unit_ref": "unit-1"}
    assert leased.work_item.status.value == "leased"
    assert connection.executed


def test_source_guard_forbids_deferred_due_selection() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py",
    ).read_text(encoding="utf-8")

    assert "'deferred'" not in source
    assert "WorkItemStatus.DEFERRED" not in source
