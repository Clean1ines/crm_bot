from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLease,
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.lease_selected_capacity_admission_work_item import (
    LeaseSelectedCapacityAdmissionWorkItem,
    LeaseSelectedCapacityAdmissionWorkItemCommand,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


def _now() -> datetime:
    return datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge.claim_builder",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="llama-3.3-70b-versatile",
    )


def _selected_work_item() -> CapacityAdmissionSelectableWorkItem:
    return CapacityAdmissionSelectableWorkItem(
        work_item_id="work-item-1",
        lane_key=_lane(),
        status="ready",
        required_window_tokens=4096,
    )


def _command() -> LeaseSelectedCapacityAdmissionWorkItemCommand:
    return LeaseSelectedCapacityAdmissionWorkItemCommand(
        selected_work_item=_selected_work_item(),
        worker=WorkerRef("capacity-admission-worker-1"),
        lease_token=LeaseToken("lease-token-1"),
        lease_expires_at=_now() + timedelta(minutes=5),
        now=_now(),
    )


def _leased_execution_record(
    *,
    work_item_id: str = "work-item-1",
) -> LeasedWorkItemRecord:
    return LeasedWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=WorkKind("knowledge.claim_builder"),
            status=WorkItemStatus.LEASED,
            attempt_count=1,
            leased_by=WorkerRef("capacity-admission-worker-1"),
            lease_token=LeaseToken("lease-token-1"),
            lease_expires_at=_now() + timedelta(minutes=5),
        ),
        schedule_payload={"payload": "value"},
    )


def _projection_lease_result(
    *,
    event_id: UUID | None = None,
) -> CapacityAdmissionProjectionLeaseResult:
    return CapacityAdmissionProjectionLeaseResult(
        work_item_id="work-item-1",
        lane_key=_lane(),
        previous_status="ready",
        status="leased",
        event_id=uuid4() if event_id is None else event_id,
    )


@dataclass(slots=True)
class FakeExecutionLeaseRepository:
    leased_record: LeasedWorkItemRecord | None
    calls: list[Mapping[str, object]] = field(default_factory=list)

    async def lease_due_work_item_by_id(
        self,
        *,
        work_kind: WorkKind,
        work_item_id: str,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        self.calls.append(
            {
                "work_kind": work_kind,
                "work_item_id": work_item_id,
                "worker": worker,
                "lease_token": lease_token,
                "lease_expires_at": lease_expires_at,
                "now": now,
            }
        )
        return self.leased_record


@dataclass(slots=True)
class FakeProjectionAdmitter:
    projection_result: CapacityAdmissionProjectionLeaseResult | None
    leases: list[CapacityAdmissionProjectionLease] = field(default_factory=list)

    async def admit_projection_work_item(
        self,
        lease: CapacityAdmissionProjectionLease,
    ) -> CapacityAdmissionProjectionLeaseResult | None:
        self.leases.append(lease)
        return self.projection_result


@pytest.mark.asyncio
async def test_leases_execution_work_item_then_admits_projection_row() -> None:
    execution_lease = _leased_execution_record()
    projection_lease = _projection_lease_result()
    execution_repository = FakeExecutionLeaseRepository(execution_lease)
    projection_admitter = FakeProjectionAdmitter(projection_lease)

    result = await LeaseSelectedCapacityAdmissionWorkItem(
        execution_lease_repository=execution_repository,
        projection_admitter=projection_admitter,
    ).execute(_command())

    assert result.leased is True
    assert result.execution_lease == execution_lease
    assert result.projection_lease == projection_lease
    assert result.skipped_reason is None

    assert execution_repository.calls == [
        {
            "work_kind": WorkKind("knowledge.claim_builder"),
            "work_item_id": "work-item-1",
            "worker": WorkerRef("capacity-admission-worker-1"),
            "lease_token": LeaseToken("lease-token-1"),
            "lease_expires_at": _now() + timedelta(minutes=5),
            "now": _now(),
        }
    ]
    assert projection_admitter.leases == [
        CapacityAdmissionProjectionLease(
            work_item_id="work-item-1",
            lane_key=_lane(),
            leased_at=_now(),
        )
    ]


@pytest.mark.asyncio
async def test_does_not_admit_projection_when_execution_lease_fails() -> None:
    execution_repository = FakeExecutionLeaseRepository(leased_record=None)
    projection_admitter = FakeProjectionAdmitter(_projection_lease_result())

    result = await LeaseSelectedCapacityAdmissionWorkItem(
        execution_lease_repository=execution_repository,
        projection_admitter=projection_admitter,
    ).execute(_command())

    assert result.leased is False
    assert result.execution_lease is None
    assert result.projection_lease is None
    assert result.skipped_reason == "execution_work_item_not_leased"
    assert len(execution_repository.calls) == 1
    assert projection_admitter.leases == []


@pytest.mark.asyncio
async def test_reports_projection_conflict_after_execution_lease() -> None:
    execution_lease = _leased_execution_record()
    execution_repository = FakeExecutionLeaseRepository(execution_lease)
    projection_admitter = FakeProjectionAdmitter(projection_result=None)

    result = await LeaseSelectedCapacityAdmissionWorkItem(
        execution_lease_repository=execution_repository,
        projection_admitter=projection_admitter,
    ).execute(_command())

    assert result.leased is False
    assert result.execution_lease == execution_lease
    assert result.projection_lease is None
    assert result.skipped_reason == "capacity_projection_not_admitted"
    assert len(projection_admitter.leases) == 1


def test_rejects_naive_timestamps() -> None:
    naive_now = datetime(2026, 6, 24, 12, 0)

    with pytest.raises(ValueError, match="now"):
        LeaseSelectedCapacityAdmissionWorkItemCommand(
            selected_work_item=_selected_work_item(),
            worker=WorkerRef("capacity-admission-worker-1"),
            lease_token=LeaseToken("lease-token-1"),
            lease_expires_at=_now() + timedelta(minutes=5),
            now=naive_now,
        )


def test_rejects_expired_lease_deadline() -> None:
    with pytest.raises(ValueError, match="lease_expires_at must be after now"):
        LeaseSelectedCapacityAdmissionWorkItemCommand(
            selected_work_item=_selected_work_item(),
            worker=WorkerRef("capacity-admission-worker-1"),
            lease_token=LeaseToken("lease-token-1"),
            lease_expires_at=_now(),
            now=_now(),
        )
