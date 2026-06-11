from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRecord,
    WorkItemAttemptDispatchRepositoryPort,
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
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityAllocationSlot,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartLlmAdmittedWorkItemAttempts,
    StartLlmAdmittedWorkItemAttemptsCommand,
)


@dataclass(slots=True)
class FakeDispatchRepository(WorkItemAttemptDispatchRepositoryPort):
    saved: list[WorkItemAttemptDispatchRecord] = field(default_factory=list)

    async def save_started_dispatch_attempt(
        self,
        record: WorkItemAttemptDispatchRecord,
    ) -> None:
        self.saved.append(record)


def _started_at() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _execution_settings() -> LlmModelExecutionSettings:
    return LlmModelExecutionSettings(reasoning_enabled=False)


def _leased_item(
    *,
    work_item_id: str = "work-1",
    attempt_count: int = 2,
    status: WorkItemStatus = WorkItemStatus.LEASED,
    lease_token: LeaseToken | None = LeaseToken("lease-token-1"),
    leased_by: WorkerRef | None = WorkerRef("worker-1"),
) -> LlmAdmittedLeasedWorkItem:
    return LlmAdmittedLeasedWorkItem(
        leased=LeasedWorkItemRecord(
            work_item=WorkItem(
                work_item_id=work_item_id,
                work_kind=_work_kind(),
                status=status,
                attempt_count=attempt_count,
                leased_by=leased_by,
                lease_token=lease_token,
                lease_expires_at=datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc),
            ),
            schedule_payload={"source_unit_ref": "unit-1"},
        ),
        allocation=LlmCapacityAllocationSlot(
            provider="groq",
            account_ref="org-1",
            model_ref="qwen-32b",
            slot_index=0,
        ),
        execution_settings=_execution_settings(),
    )


def _invalid_leased_item(
    *,
    status: WorkItemStatus = WorkItemStatus.LEASED,
    lease_token: LeaseToken | None = LeaseToken("lease-token-1"),
    leased_by: WorkerRef | None = WorkerRef("worker-1"),
) -> LlmAdmittedLeasedWorkItem:
    work_item = WorkItem(
        work_item_id="work-1",
        work_kind=_work_kind(),
        status=WorkItemStatus.LEASED,
        attempt_count=2,
        leased_by=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-token-1"),
        lease_expires_at=datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc),
    )
    object.__setattr__(work_item, "status", status)
    object.__setattr__(work_item, "lease_token", lease_token)
    object.__setattr__(work_item, "leased_by", leased_by)

    leased_record = object.__new__(LeasedWorkItemRecord)
    object.__setattr__(leased_record, "work_item", work_item)
    object.__setattr__(leased_record, "schedule_payload", {"source_unit_ref": "unit-1"})

    return LlmAdmittedLeasedWorkItem(
        leased=leased_record,
        allocation=LlmCapacityAllocationSlot(
            provider="groq",
            account_ref="org-1",
            model_ref="qwen-32b",
            slot_index=0,
        ),
        execution_settings=_execution_settings(),
    )


@pytest.mark.asyncio
async def test_creates_deterministic_attempt_id_from_work_item_and_attempt_count() -> (
    None
):
    repository = FakeDispatchRepository()

    result = await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
        StartLlmAdmittedWorkItemAttemptsCommand(
            leased_items=(_leased_item(work_item_id="work-1", attempt_count=2),),
            started_at=_started_at(),
        ),
    )

    assert result.started_attempts[0].attempt_id == "work-1:attempt:2"
    assert repository.saved[0].attempt_id == "work-1:attempt:2"
    assert repository.saved[0].attempt_number == 2


@pytest.mark.asyncio
async def test_saves_schedule_payload_and_llm_allocation_payload() -> None:
    repository = FakeDispatchRepository()

    await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
        StartLlmAdmittedWorkItemAttemptsCommand(
            leased_items=(_leased_item(),),
            started_at=_started_at(),
        ),
    )

    record = repository.saved[0]
    assert record.schedule_payload == {"source_unit_ref": "unit-1"}
    assert record.llm_allocation_payload == {
        "provider": "groq",
        "account_ref": "org-1",
        "model_ref": "qwen-32b",
        "slot_index": 0,
    }
    assert record.dispatch_payload == {
        "work_item_id": "work-1",
        "schedule_payload": {"source_unit_ref": "unit-1"},
        "llm_allocation": {
            "provider": "groq",
            "account_ref": "org-1",
            "model_ref": "qwen-32b",
            "slot_index": 0,
        },
        "llm_execution_settings": {"reasoning_enabled": False},
    }


@pytest.mark.asyncio
async def test_started_dispatch_attempt_preserves_llm_execution_settings() -> None:
    repository = FakeDispatchRepository()

    result = await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
        StartLlmAdmittedWorkItemAttemptsCommand(
            leased_items=(_leased_item(),),
            started_at=_started_at(),
        ),
    )

    assert result.started_attempts[0].dispatch_payload["llm_execution_settings"] == {
        "reasoning_enabled": False,
    }
    assert repository.saved[0].dispatch_payload["llm_execution_settings"] == {
        "reasoning_enabled": False,
    }


@pytest.mark.asyncio
async def test_returns_started_attempts() -> None:
    repository = FakeDispatchRepository()

    result = await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
        StartLlmAdmittedWorkItemAttemptsCommand(
            leased_items=(
                _leased_item(work_item_id="work-1"),
                _leased_item(work_item_id="work-2"),
            ),
            started_at=_started_at(),
        ),
    )

    assert tuple(attempt.work_item_id for attempt in result.started_attempts) == (
        "work-1",
        "work-2",
    )
    assert len(repository.saved) == 2


@pytest.mark.asyncio
async def test_empty_leased_items_returns_empty_result_and_does_not_call_repository() -> (
    None
):
    repository = FakeDispatchRepository()

    result = await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
        StartLlmAdmittedWorkItemAttemptsCommand(
            leased_items=(),
            started_at=_started_at(),
        ),
    )

    assert result.started_attempts == ()
    assert repository.saved == []


def test_rejects_naive_started_at() -> None:
    with pytest.raises(ValueError, match="started_at must be timezone-aware"):
        StartLlmAdmittedWorkItemAttemptsCommand(
            leased_items=(),
            started_at=datetime(2026, 6, 10, 12, 0),
        )


@pytest.mark.asyncio
async def test_rejects_non_leased_work_item() -> None:
    repository = FakeDispatchRepository()

    with pytest.raises(ValueError, match="work_item must be leased"):
        await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
            StartLlmAdmittedWorkItemAttemptsCommand(
                leased_items=(_invalid_leased_item(status=WorkItemStatus.READY),),
                started_at=_started_at(),
            ),
        )


@pytest.mark.asyncio
async def test_rejects_leased_item_without_lease_token() -> None:
    repository = FakeDispatchRepository()

    with pytest.raises(ValueError, match="leased work_item must have lease_token"):
        await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
            StartLlmAdmittedWorkItemAttemptsCommand(
                leased_items=(_invalid_leased_item(lease_token=None),),
                started_at=_started_at(),
            ),
        )


@pytest.mark.asyncio
async def test_rejects_leased_item_without_leased_by() -> None:
    repository = FakeDispatchRepository()

    with pytest.raises(ValueError, match="leased work_item must have leased_by"):
        await StartLlmAdmittedWorkItemAttempts(repository=repository).execute(
            StartLlmAdmittedWorkItemAttemptsCommand(
                leased_items=(_invalid_leased_item(leased_by=None),),
                started_at=_started_at(),
            ),
        )
