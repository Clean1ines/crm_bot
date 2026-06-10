from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.capacity_runtime.domain.capacity_decision import (
    CapacityAvailability,
    CapacityNeed,
    CapacityResourceKind,
    CapacitySnapshot,
    CapacityWorkClass,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.lease_admitted_work_items import (
    LeaseAdmittedWorkItems,
    LeaseAdmittedWorkItemsCommand,
    LeaseAdmittedWorkItemsResult,
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
    queue: list[LeasedWorkItemRecord] = field(default_factory=list)
    lease_tokens: list[LeaseToken] = field(default_factory=list)

    async def lease_due_work_item(
        self,
        *,
        work_kind: WorkKind,
        worker: WorkerRef,
        lease_token: LeaseToken,
        lease_expires_at: datetime,
        now: datetime,
    ) -> LeasedWorkItemRecord | None:
        self.lease_tokens.append(lease_token)
        if not self.queue:
            return None
        return self.queue.pop(0)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("generic.execution.work")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _needs() -> tuple[CapacityNeed, ...]:
    return (CapacityNeed(CapacityResourceKind.WORKER_SLOT, 1),)


def _snapshot(available: int) -> CapacitySnapshot:
    return CapacitySnapshot(
        availability=(
            CapacityAvailability(CapacityResourceKind.WORKER_SLOT, available),
        ),
    )


def _record(work_item_id: str) -> LeasedWorkItemRecord:
    return LeasedWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=_work_kind(),
            status=WorkItemStatus.LEASED,
            attempt_count=1,
            leased_by=_worker(),
            lease_token=LeaseToken(f"lease:{work_item_id}"),
            lease_expires_at=_lease_expires_at(),
        ),
        schedule_payload={"work_item_id": work_item_id},
    )


def _command(*, requested_items: int, available: int) -> LeaseAdmittedWorkItemsCommand:
    return LeaseAdmittedWorkItemsCommand(
        work_kind=_work_kind(),
        work_class=CapacityWorkClass.IO_BOUND,
        capacity_needs=_needs(),
        capacity_snapshot=_snapshot(available),
        requested_items=requested_items,
        worker=_worker(),
        lease_token_prefix="lease-prefix",
        lease_expires_at=_lease_expires_at(),
        now=_now(),
    )


@pytest.mark.asyncio
async def test_leases_up_to_capacity_decision_max_admissible_items() -> None:
    repository = FakeLeaseRepository(
        queue=[_record("work-1"), _record("work-2"), _record("work-3")],
    )

    result = await LeaseAdmittedWorkItems(
        repository=repository,
        capacity_policy=CapacityAdmissionPolicy(),
    ).execute(_command(requested_items=5, available=2))

    assert result.capacity_decision.max_admissible_items == 2
    assert tuple(item.work_item.work_item_id for item in result.leased) == (
        "work-1",
        "work-2",
    )
    assert repository.lease_tokens == [
        LeaseToken("lease-prefix:0"),
        LeaseToken("lease-prefix:1"),
    ]


@pytest.mark.asyncio
async def test_does_not_lease_when_capacity_rejected() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    result = await LeaseAdmittedWorkItems(
        repository=repository,
        capacity_policy=CapacityAdmissionPolicy(),
    ).execute(_command(requested_items=5, available=0))

    assert result.capacity_decision.max_admissible_items == 0
    assert result.leased == ()
    assert repository.lease_tokens == []


@pytest.mark.asyncio
async def test_stops_early_when_no_due_work_item() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    result = await LeaseAdmittedWorkItems(
        repository=repository,
        capacity_policy=CapacityAdmissionPolicy(),
    ).execute(_command(requested_items=5, available=3))

    assert result.capacity_decision.max_admissible_items == 3
    assert tuple(item.work_item.work_item_id for item in result.leased) == ("work-1",)
    assert repository.lease_tokens == [
        LeaseToken("lease-prefix:0"),
        LeaseToken("lease-prefix:1"),
    ]


@pytest.mark.asyncio
async def test_generates_deterministic_lease_tokens_from_prefix_and_index() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1"), _record("work-2")])

    await LeaseAdmittedWorkItems(
        repository=repository,
        capacity_policy=CapacityAdmissionPolicy(),
    ).execute(_command(requested_items=2, available=2))

    assert repository.lease_tokens == [
        LeaseToken("lease-prefix:0"),
        LeaseToken("lease-prefix:1"),
    ]


def test_rejects_invalid_requested_items() -> None:
    with pytest.raises(ValueError, match="requested_items must be > 0"):
        _command(requested_items=0, available=1)


def test_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        LeaseAdmittedWorkItemsCommand(
            work_kind=_work_kind(),
            work_class=CapacityWorkClass.IO_BOUND,
            capacity_needs=_needs(),
            capacity_snapshot=_snapshot(available=1),
            requested_items=1,
            worker=_worker(),
            lease_token_prefix="lease-prefix",
            lease_expires_at=_lease_expires_at(),
            now=datetime(2026, 6, 10, 12, 0),
        )


def test_result_length_never_exceeds_max_admissible_items() -> None:
    decision = CapacityAdmissionPolicy().decide(
        request=__import__(
            "src.contexts.capacity_runtime.domain.capacity_decision",
            fromlist=["CapacityRequest"],
        ).CapacityRequest(
            work_class=CapacityWorkClass.IO_BOUND,
            needs=_needs(),
            requested_items=1,
        ),
        snapshot=_snapshot(available=1),
    )

    with pytest.raises(ValueError, match="leased length must not exceed"):
        LeaseAdmittedWorkItemsResult(
            capacity_decision=decision,
            leased=(_record("work-1"), _record("work-2")),
        )


def test_fake_record_payload_is_generic_mapping() -> None:
    payload: Mapping[str, object] = _record("work-1").schedule_payload
    assert payload == {"work_item_id": "work-1"}
