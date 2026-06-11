from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.lease_due_work_item import (
    LeaseDueWorkItem,
    LeaseDueWorkItemCommand,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(slots=True)
class FakeLeaseRepository(WorkItemLeaseRepositoryPort):
    leased: LeasedWorkItemRecord | None = None
    calls: list[tuple[WorkKind, WorkerRef, LeaseToken, datetime, datetime]] | None = (
        None
    )

    async def lease_due_work_item(
        self,
        *,
        work_kind: WorkKind,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        if self.calls is None:
            self.calls = []
        self.calls.append((work_kind, worker, lease_token, lease_expires_at, now))
        return self.leased


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _lease_token() -> LeaseToken:
    return LeaseToken("lease-token-1")


def _command() -> LeaseDueWorkItemCommand:
    return LeaseDueWorkItemCommand(
        work_kind=_work_kind(),
        worker=_worker(),
        lease_token=_lease_token(),
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )


def _leased_record() -> LeasedWorkItemRecord:
    return LeasedWorkItemRecord(
        work_item=WorkItem(
            work_item_id="work-1",
            work_kind=_work_kind(),
            status=WorkItemStatus.LEASED,
            attempt_count=1,
            leased_by=_worker(),
            lease_token=_lease_token(),
            lease_expires_at=_lease_expires_at(),
        ),
        schedule_payload={"source_unit_ref": "source-unit-1"},
    )


@pytest.mark.asyncio
async def test_returns_none_when_repo_finds_no_item() -> None:
    repository = FakeLeaseRepository()

    result = await LeaseDueWorkItem(repository=repository).execute(_command())

    assert result.leased is None
    assert repository.calls == [
        (_work_kind(), _worker(), _lease_token(), _lease_expires_at(), _now()),
    ]


@pytest.mark.asyncio
async def test_returns_leased_record_when_repo_leases_item() -> None:
    leased = _leased_record()
    repository = FakeLeaseRepository(leased=leased)

    result = await LeaseDueWorkItem(repository=repository).execute(_command())

    assert result.leased == leased
    assert result.leased.schedule_payload == {"source_unit_ref": "source-unit-1"}


def test_rejects_lease_expires_at_not_after_now() -> None:
    with pytest.raises(ValueError, match="lease_expires_at must be > now"):
        LeaseDueWorkItemCommand(
            work_kind=_work_kind(),
            worker=_worker(),
            lease_token=_lease_token(),
            lease_expires_at=_now(),
            now=_now(),
        )


def test_rejects_naive_now() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        LeaseDueWorkItemCommand(
            work_kind=_work_kind(),
            worker=_worker(),
            lease_token=_lease_token(),
            lease_expires_at=_lease_expires_at(),
            now=datetime(2026, 6, 10, 12, 0),
        )


def test_rejects_naive_lease_expires_at() -> None:
    with pytest.raises(ValueError, match="lease_expires_at must be timezone-aware"):
        LeaseDueWorkItemCommand(
            work_kind=_work_kind(),
            worker=_worker(),
            lease_token=_lease_token(),
            lease_expires_at=datetime(2026, 6, 10, 12, 5),
            now=_now(),
        )


def test_rejects_wrong_value_object_types() -> None:
    with pytest.raises(TypeError, match="work_kind must be WorkKind"):
        LeaseDueWorkItemCommand(
            work_kind="bad",
            worker=_worker(),
            lease_token=_lease_token(),
            lease_expires_at=_lease_expires_at(),
            now=_now(),
        )


def test_leased_record_rejects_non_leased_work_item() -> None:
    with pytest.raises(ValueError, match="work_item must be leased"):
        LeasedWorkItemRecord(
            work_item=WorkItem(
                work_item_id="work-1",
                work_kind=_work_kind(),
            ),
            schedule_payload={},
        )


def test_leased_record_rejects_non_mapping_payload() -> None:
    with pytest.raises(TypeError, match="schedule_payload must be Mapping"):
        LeasedWorkItemRecord(
            work_item=_leased_record().work_item,
            schedule_payload=("not", "mapping"),
        )


def test_application_use_case_has_no_infrastructure_imports() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/execution_runtime/application/use_cases/lease_due_work_item.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "infrastructure",
        "postgres",
        "asyncpg",
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
    )
    for marker in forbidden:
        assert marker not in source
