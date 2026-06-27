from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
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
    LlmCapacityProjectionCommand,
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LeaseLlmAdmittedWorkItems,
    LeaseLlmAdmittedWorkItemsCommand,
)


@dataclass(slots=True)
class FakeLeaseRepository(WorkItemLeaseRepositoryPort):
    queue: list[LeasedWorkItemRecord] = field(default_factory=list)
    lease_tokens: list[LeaseToken] = field(default_factory=list)
    peek_calls: int = 0

    async def peek_due_work_items(
        self,
        *,
        work_kind: WorkKind,
        requested_items: int,
        now: datetime,
    ) -> tuple[DueWorkItemRecord, ...]:
        self.peek_calls += 1
        del work_kind, now
        return tuple(
            _due_record(record.work_item.work_item_id)
            for record in self.queue[:requested_items]
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
        self.lease_tokens.append(lease_token)
        if not self.queue:
            return None
        return self.queue.pop(0)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _profile() -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        input_tokens=3000,
        artifact_tokens=500,
    )


def _account(
    *,
    account_ref: str,
    minute_requests: int,
    minute_tokens: int,
    model_ref: str = "qwen/qwen3-32b",
    daily_requests: int = 100,
    daily_tokens: int = 50000,
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref=model_ref,
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
    )


def _due_record(work_item_id: str) -> DueWorkItemRecord:
    return DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=_work_kind(),
            status=WorkItemStatus.READY,
            attempt_count=0,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
        ),
        schedule_payload={"source_unit_ref": f"{work_item_id}:source"},
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


def _pre_lease_records_for_queue(
    queue: list[LeasedWorkItemRecord],
) -> tuple[DueWorkItemRecord, ...]:
    return tuple(_due_record(record.work_item.work_item_id) for record in queue)


def _retryable_due_record(work_item_id: str) -> DueWorkItemRecord:
    return DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=_work_kind(),
            status=WorkItemStatus.RETRYABLE_FAILED,
            attempt_count=1,
            leased_by=None,
            lease_token=None,
            lease_expires_at=None,
        ),
        schedule_payload={"source_unit_ref": f"{work_item_id}:source"},
    )


def _command(
    *,
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    requested_items: int,
    active_model_ref: str = "qwen/qwen3-32b",
    now: datetime | None = None,
    pre_lease_due_records: tuple[DueWorkItemRecord, ...] = (),
) -> LeaseLlmAdmittedWorkItemsCommand:
    return LeaseLlmAdmittedWorkItemsCommand(
        work_kind=_work_kind(),
        profile=_profile(),
        account_capacities=account_capacities,
        active_model_ref=active_model_ref,
        requested_items=requested_items,
        worker=_worker(),
        lease_token_prefix="lease-prefix",
        lease_expires_at=_lease_expires_at(),
        now=now or _now(),
        pre_lease_due_records=pre_lease_due_records,
    )


def _command_for_repository(
    repository: FakeLeaseRepository,
    *,
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    requested_items: int,
    active_model_ref: str = "qwen/qwen3-32b",
    now: datetime | None = None,
) -> LeaseLlmAdmittedWorkItemsCommand:
    return _command(
        account_capacities=account_capacities,
        requested_items=requested_items,
        active_model_ref=active_model_ref,
        now=now,
        pre_lease_due_records=_pre_lease_records_for_queue(repository.queue),
    )


def _use_case(repository: FakeLeaseRepository) -> LeaseLlmAdmittedWorkItems:
    return LeaseLlmAdmittedWorkItems(
        lease_repository=repository,
        capacity_policy=CapacityAdmissionPolicy(),
        active_model_capacity_selector=SelectActiveLlmModelCapacity(
            projector=ProjectLlmCapacityToCapacityRuntime(),
        ),
        route_catalog=default_groq_llm_model_route_catalog(),
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
        _command_for_repository(
            repository,
            account_capacities=(
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

    assert repository.peek_calls == 0

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
            "model_ref": "qwen/qwen3-32b",
            "slot_index": 0,
        },
        "llm_execution_settings": {"reasoning_enabled": False},
    }


@pytest.mark.asyncio
async def test_qwen_active_model_uses_reasoning_disabled_execution_settings() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    result = await _use_case(repository).execute(
        _command_for_repository(
            repository,
            account_capacities=(
                _account(
                    account_ref="account_1",
                    minute_requests=1,
                    minute_tokens=3500,
                ),
            ),
            requested_items=1,
        ),
    )

    item = result.leased[0]
    assert item.execution_settings.to_provider_options() == {"reasoning_enabled": False}
    assert item.to_dispatch_payload()["llm_execution_settings"] == {
        "reasoning_enabled": False,
    }


@pytest.mark.asyncio
async def test_no_due_work_items_returns_no_assigned_items_even_when_capacity_exists() -> (
    None
):
    repository = FakeLeaseRepository()

    result = await _use_case(repository).execute(
        _command(
            account_capacities=(
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
            account_capacities=(
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
        _command_for_repository(
            repository,
            account_capacities=(
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
        _command_for_repository(
            repository,
            account_capacities=(
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
            account_capacities=(
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
            account_capacities=(
                _account(
                    account_ref="account_1", minute_requests=1, minute_tokens=3500
                ),
            ),
            requested_items=0,
        )


@pytest.mark.asyncio
async def test_uses_only_active_model_accounts() -> None:
    repository = FakeLeaseRepository(
        queue=[
            _record("work-1"),
            _record("work-2"),
            _record("work-3"),
            _record("work-4"),
            _record("work-5"),
        ],
    )

    result = await _use_case(repository).execute(
        _command_for_repository(
            repository,
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="qwen_2",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="fallback_openai",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="openai/gpt-oss-120b",
                ),
                _account(
                    account_ref="fallback_llama",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="llama-3.3-70b-versatile",
                ),
            ),
            active_model_ref="qwen/qwen3-32b",
            requested_items=10,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 3
    assert len(repository.lease_tokens) == 3
    assert len(result.leased) == 3
    assert {item.allocation.model_ref for item in result.leased} == {
        "qwen/qwen3-32b",
    }
    assert [item.allocation.account_ref for item in result.leased] == [
        "qwen_1",
        "qwen_1",
        "qwen_2",
    ]


@pytest.mark.asyncio
async def test_active_fallback_model_can_be_selected_explicitly() -> None:
    repository = FakeLeaseRepository(
        queue=[
            _record("work-1"),
            _record("work-2"),
            _record("work-3"),
        ],
    )

    result = await _use_case(repository).execute(
        _command_for_repository(
            repository,
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="openai_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="openai/gpt-oss-120b",
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=10,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 2
    assert [item.allocation.account_ref for item in result.leased] == [
        "openai_1",
        "openai_1",
    ]
    assert {item.allocation.model_ref for item in result.leased} == {
        "openai/gpt-oss-120b",
    }


@pytest.mark.asyncio
async def test_absent_active_model_yields_zero_lease() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    result = await _use_case(repository).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="qwen/qwen3-32b",
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=10,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 0
    assert repository.lease_tokens == []
    assert result.leased == ()


@pytest.mark.asyncio
async def test_mixed_model_capacities_do_not_raise_in_composition() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    result = await _use_case(repository).execute(
        _command_for_repository(
            repository,
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="openai_1",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="openai/gpt-oss-120b",
                ),
            ),
            active_model_ref="qwen/qwen3-32b",
            requested_items=2,
        ),
    )

    assert result.llm_capacity_projection.max_projected_items == 1
    assert len(result.leased) == 1


@pytest.mark.asyncio
async def test_unknown_active_model_in_catalog_raises_before_assignment() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    with pytest.raises(ValueError, match="model_ref is not in route catalog"):
        await _use_case(repository).execute(
            _command_for_repository(
                repository,
                account_capacities=(
                    _account(
                        account_ref="custom_1",
                        minute_requests=10,
                        minute_tokens=3500,
                        model_ref="custom/model",
                    ),
                ),
                active_model_ref="custom/model",
                requested_items=1,
            ),
        )

    assert repository.lease_tokens == []


@pytest.mark.asyncio
async def test_selection_kind_matches_pre_lease_retryable_status() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-retry-1")])

    result = await _use_case(repository).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="account_1",
                    minute_requests=1,
                    minute_tokens=3500,
                ),
            ),
            requested_items=1,
            pre_lease_due_records=(_retryable_due_record("work-retry-1"),),
        ),
    )

    assert repository.peek_calls == 0
    assert len(result.leased) == 1
    assert result.leased[0].selection_kind == "retryable"


@pytest.mark.asyncio
async def test_leased_work_item_requires_matching_pre_lease_record() -> None:
    repository = FakeLeaseRepository(queue=[_record("work-1")])

    with pytest.raises(
        ValueError,
        match="leased work item missing pre-lease admission selection_kind",
    ):
        await _use_case(repository).execute(
            _command(
                account_capacities=(
                    _account(
                        account_ref="account_1",
                        minute_requests=1,
                        minute_tokens=3500,
                    ),
                ),
                requested_items=1,
                pre_lease_due_records=(),
            ),
        )


def test_direct_projector_still_rejects_mixed_model_capacities() -> None:
    with pytest.raises(
        ValueError,
        match="capacity projection accounts must use one active model_ref",
    ):
        ProjectLlmCapacityToCapacityRuntime().execute(
            LlmCapacityProjectionCommand(
                profile=_profile(),
                accounts=(
                    _account(
                        account_ref="qwen_1",
                        minute_requests=10,
                        minute_tokens=3500,
                        model_ref="qwen/qwen3-32b",
                    ),
                    _account(
                        account_ref="openai_1",
                        minute_requests=10,
                        minute_tokens=3500,
                        model_ref="openai/gpt-oss-120b",
                    ),
                ),
                requested_items=2,
            ),
        )
