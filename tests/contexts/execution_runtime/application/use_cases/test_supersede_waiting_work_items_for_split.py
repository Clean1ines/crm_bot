from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from src.contexts.execution_runtime.application.use_cases.supersede_waiting_work_items_for_split import (
    SupersedeWaitingWorkItemsForSplit,
    SupersedeWaitingWorkItemsForSplitCommand,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    InvalidWorkItemTransition,
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


@dataclass(slots=True)
class FakeSplitSupersedeRepository:
    items: dict[str, WorkItem]
    loaded_ids: list[str] = field(default_factory=list)
    saved_items: list[WorkItem] = field(default_factory=list)

    async def load_work_item(self, work_item_id: str) -> WorkItem | None:
        self.loaded_ids.append(work_item_id)
        return self.items.get(work_item_id)

    async def save_work_item(self, item: WorkItem) -> None:
        self.saved_items.append(item)
        self.items[item.work_item_id] = item


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _ready_item(work_item_id: str = "work-1") -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        work_kind=_work_kind(),
    )


def _leased_item(work_item_id: str = "work-1") -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        _ready_item(work_item_id),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken(f"lease-{work_item_id}"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )


def _now():
    from datetime import datetime, timezone

    return datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


def _deferred_item(work_item_id: str = "work-1") -> WorkItem:
    return WorkItemStateMachine.defer_leased(
        _leased_item(work_item_id),
        wait_until=WaitUntil(_now() + timedelta(seconds=60)),
        error_kind="minute_limit",
    )


def _retryable_failed_item(work_item_id: str = "work-1") -> WorkItem:
    return WorkItemStateMachine.fail_leased_retryable(
        _leased_item(work_item_id),
        error_kind="network_timeout",
        next_attempt_at=WaitUntil(_now() + timedelta(seconds=10)),
    )


@pytest.mark.asyncio
async def test_loads_all_ids_and_supersedes_waiting_items() -> None:
    repository = FakeSplitSupersedeRepository(
        items={
            "work-1": _ready_item("work-1"),
            "work-2": _deferred_item("work-2"),
            "work-3": _retryable_failed_item("work-3"),
        }
    )

    result = await SupersedeWaitingWorkItemsForSplit(
        repository=repository,
    ).execute(
        SupersedeWaitingWorkItemsForSplitCommand(
            work_item_ids=("work-1", "work-2", "work-3"),
        )
    )

    assert repository.loaded_ids == ["work-1", "work-2", "work-3"]
    assert result.superseded_work_item_ids == ("work-1", "work-2", "work-3")
    assert tuple(item.work_item_id for item in repository.saved_items) == (
        "work-1",
        "work-2",
        "work-3",
    )
    assert all(
        item.status is WorkItemStatus.SPLIT_SUPERSEDED
        for item in repository.saved_items
    )


@pytest.mark.asyncio
async def test_raises_if_item_missing() -> None:
    repository = FakeSplitSupersedeRepository(items={})

    with pytest.raises(ValueError, match="work item not found: missing-work"):
        await SupersedeWaitingWorkItemsForSplit(
            repository=repository,
        ).execute(
            SupersedeWaitingWorkItemsForSplitCommand(
                work_item_ids=("missing-work",),
            )
        )

    assert repository.saved_items == []


@pytest.mark.asyncio
async def test_raises_if_item_in_invalid_status() -> None:
    repository = FakeSplitSupersedeRepository(items={"work-1": _leased_item("work-1")})

    with pytest.raises(InvalidWorkItemTransition):
        await SupersedeWaitingWorkItemsForSplit(
            repository=repository,
        ).execute(
            SupersedeWaitingWorkItemsForSplitCommand(
                work_item_ids=("work-1",),
            )
        )

    assert repository.saved_items == []


def test_command_requires_non_empty_work_item_ids() -> None:
    with pytest.raises(ValueError, match="work_item_ids must be non-empty"):
        SupersedeWaitingWorkItemsForSplitCommand(work_item_ids=())

    with pytest.raises(ValueError, match="work_item_ids must contain non-empty text"):
        SupersedeWaitingWorkItemsForSplitCommand(work_item_ids=(" ",))
