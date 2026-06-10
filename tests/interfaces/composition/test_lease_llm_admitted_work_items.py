from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LeaseLlmAdmittedWorkItems,
    LeaseLlmAdmittedWorkItemsCommand,
)


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
    return WorkKind("knowledge_workbench.draft_observation_extraction")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _profile() -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        estimated_prompt_tokens=3000,
        estimated_completion_tokens=500,
    )


def _account(
    *,
    account_ref: str,
    minute_requests: int,
    minute_tokens: int,
    daily_requests: int = 100,
    daily_tokens: int = 50000,
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen-32b",
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
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
        schedule_payload={"source_unit_ref": f"{work_item_id}:source"},
    )


def _command(
    *,
    accounts: tuple[LlmProviderAccountCapacity, ...],
    requested_items: int,
    now: datetime | None = None,
) -> LeaseLlmAdmittedWorkItemsCommand:
    return LeaseLlmAdmittedWorkItemsCommand(
        work_kind=_work_kind(),
        profile=_profile(),
        accounts=accounts,
        requested_items=requested_items,
        worker=_worker(),
        lease_token_prefix="lease-prefix",
        lease_expires_at=_lease_expires_at(),
        now=now or _now(),
    )


def _use_case(repository: FakeLeaseRepository) -> LeaseLlmAdmittedWorkItems:
    return LeaseLlmAdmittedWorkItems(
        lease_repository=repository,
        capacity_policy=CapacityAdmissionPolicy(),
        llm_capacity_projector=ProjectLlmCapacityToCapacityRuntime(),
    )


@pytest.mark.asyncio
async def test_assigns_allocation_slots_to_leased_work_items() -> None:
    repository = FakeLeaseRepository(
        queue=[
            _record("work-1"),
            _record("work-2"),
            _record("work-3"),
            _record("work-4"),
        ],
    )

    result = await _use_case(repository).execute(
        _command(
            accounts=(
                _account(
                    account_ref="account_1", minute_requests=2, minute_tokens=7000
                ),
                _account(
                    account_ref="account_2", minute_requests=2, minute_tokens=7000
                ),
            ),
            requested_items=4,
        ),
    )

    assert len(result.leased) == 4
    assert [item.allocation.account_ref for item in result.leased] == [
        "account_1",
        "account_1",
        "account_2",
        "account_2",
    ]

    payload = result.leased[0].to_dispatch_payload()
    assert payload == {
        "work_item_id": "work-1",
        "schedule_payload": {"source_unit_ref": "work-1:source"},
        "llm_allocation": {
            "provider": "groq",
            "account_ref": "account_1",
            "model_ref": "qwen-32b",
            "slot_index": 0,
        },
    }


@pytest.mark.asyncio
async def test_no_due_work_items_returns_no_assigned_items_even_when_capacity_exists() -> (
    None
):
    repository = FakeLeaseRepository()

    result = await _use_case(repository).execute(
        _command(
            accounts=(
                _account(
                    account_ref="account_1", minute_requests=4, minute_tokens=14000
                ),
            ),
            requested_items=4,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 4
    assert result.lease_result.capacity_decision.max_admissible_items == 4
    assert result.lease_result.leased == ()
    assert result.leased == ()


@pytest.mark.asyncio
async def test_exhausted_llm_capacity_leases_nothing() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    result = await _use_case(repository).execute(
        _command(
            accounts=(
                _account(
                    account_ref="account_1",
                    minute_requests=0,
                    minute_tokens=0,
                    daily_requests=0,
                    daily_tokens=0,
                ),
            ),
            requested_items=4,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 0
    assert result.lease_result.leased == ()
    assert result.leased == ()
    assert repository.lease_tokens == []


@pytest.mark.asyncio
async def test_requested_items_caps_projection_and_leasing() -> None:
    repository = FakeLeaseRepository(
        queue=[
            _record("work-1"),
            _record("work-2"),
            _record("work-3"),
            _record("work-4"),
        ],
    )

    result = await _use_case(repository).execute(
        _command(
            accounts=(
                _account(
                    account_ref="account_1", minute_requests=10, minute_tokens=35000
                ),
            ),
            requested_items=3,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 3
    assert len(repository.lease_tokens) == 3
    assert len(result.leased) == 3


@pytest.mark.asyncio
async def test_fewer_due_items_than_allocations_uses_prefix_allocations_only() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1"), _record("work-2")])

    result = await _use_case(repository).execute(
        _command(
            accounts=(
                _account(
                    account_ref="account_1", minute_requests=5, minute_tokens=17500
                ),
            ),
            requested_items=5,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 5
    assert len(result.leased) == 2
    assert tuple(item.allocation.slot_index for item in result.leased) == (0, 1)


def test_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        _command(
            accounts=(
                _account(
                    account_ref="account_1", minute_requests=1, minute_tokens=3500
                ),
            ),
            requested_items=1,
            now=datetime(2026, 6, 10, 12, 0),
        )


def test_rejects_invalid_requested_items() -> None:
    with pytest.raises(ValueError, match="requested_items must be > 0"):
        _command(
            accounts=(
                _account(
                    account_ref="account_1", minute_requests=1, minute_tokens=3500
                ),
            ),
            requested_items=0,
        )
