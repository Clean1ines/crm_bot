from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, cast

import pytest

from src.contexts.capacity_admission_queue.application.ports.capacity_lane_claim_repository_port import (
    CapacityLaneClaim,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_window_budget_repository_port import (
    CapacityReservation,
    CapacityWindowBudgetSnapshot,
)
from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    RunCapacityWindowDrain,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    SelectCapacityAdmissionWorkItem,
)
from src.contexts.capacity_admission_queue.application.sync_capacity_admission_projection_lifecycle import (
    CapacityAdmissionProjectionLifecycleUpdate,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_drain_bridge import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
    ClaimBuilderCapacityDrainBridge,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.run_claim_builder_capacity_queue_once import (
    RunClaimBuilderCapacityQueueOnce,
    RunClaimBuilderCapacityQueueOnceCommand,
)
from tests.contexts.knowledge_workbench.application.sagas.test_claim_builder_capacity_drain_bridge import (
    FakeContextResolver,
    FakeWorkflowUnitOfWork,
)


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)


def _selection_lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        account_ref=None,
    )


def _execution_window() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        account_ref="account-1",
    )


@dataclass(slots=True)
class FakeLaneClaims:
    async def claim_dirty_lane(self, **_: object) -> CapacityLaneClaim:
        return CapacityLaneClaim(
            lane_id="claim-builder:groq:-:qwen/qwen3-32b",
            lane_key=_selection_lane(),
            claimed_by="worker-1",
            claimed_until=_now(),
            claim_version=1,
        )

    async def release_lane_claim(self, **_: object) -> None:
        return None

    async def clear_dirty_flag(self, **_: object) -> None:
        return None


@dataclass(slots=True)
class FakeBudget:
    reservations: list[CapacityReservation] = field(default_factory=list)

    async def get_window(self, **_: object) -> CapacityWindowBudgetSnapshot:
        return CapacityWindowBudgetSnapshot(
            provider="groq",
            account_ref="account-1",
            model_ref="qwen/qwen3-32b",
            remaining_minute_requests=10,
            remaining_minute_tokens=10_000,
            remaining_daily_requests=10,
            remaining_daily_tokens=10_000,
            reserved_minute_requests=0,
            reserved_minute_tokens=0,
            reserved_daily_requests=0,
            reserved_daily_tokens=0,
            minute_reset_at=None,
            daily_reset_at=None,
            frozen_until=None,
        )

    async def try_reserve(
        self,
        *,
        provider: str,
        account_ref: str | None,
        model_ref: str,
        request_count: int,
        token_count: int,
        now: datetime,
    ) -> CapacityReservation:
        reservation = CapacityReservation(
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
            request_count=request_count,
            token_count=token_count,
            reserved_at=now,
        )
        self.reservations.append(reservation)
        return reservation

    async def release_reservation(self, **_: object) -> None:
        return None

    async def apply_capacity_observation(
        self, **_: object
    ) -> CapacityWindowBudgetSnapshot:
        return await self.get_window()

    async def freeze_until(self, **_: object) -> None:
        return None


@dataclass(slots=True)
class FakeSelector:
    item: CapacityAdmissionSelectableWorkItem | None
    selection_accounts: list[str | None] = field(default_factory=list)

    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        **_: object,
    ) -> None:
        self.selection_accounts.append(lane_key.account_ref)
        return None

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        **_: object,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        self.selection_accounts.append(lane_key.account_ref)
        return self.item


@dataclass(slots=True)
class FakeLifecycle:
    updates: list[CapacityAdmissionProjectionLifecycleUpdate] = field(
        default_factory=list
    )

    async def sync_projection_lifecycle(
        self,
        update: CapacityAdmissionProjectionLifecycleUpdate,
    ) -> None:
        self.updates.append(update)


@pytest.mark.asyncio
async def test_run_once_creates_execute_command_for_ready_claim_builder_item() -> None:
    uow = FakeWorkflowUnitOfWork()
    selector = FakeSelector(_item("work-item-1"))

    result = await _runner(uow, selector).execute(_command())

    assert result.drained_count == 1
    assert result.provider_call_count == 0
    assert uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )


@pytest.mark.asyncio
async def test_run_once_uses_accountless_selection_lane_and_account_specific_execution_window() -> (
    None
):
    uow = FakeWorkflowUnitOfWork()
    selector = FakeSelector(_item("work-item-1"))

    result = await _runner(uow, selector).execute(_command())

    assert selector.selection_accounts == [None, None]
    assert result.selection_lane_key.account_ref is None
    assert result.execution_window_key.account_ref == "account-1"


@pytest.mark.asyncio
async def test_run_once_does_not_create_prepare_command() -> None:
    uow = FakeWorkflowUnitOfWork()

    await _runner(uow, FakeSelector(_item("work-item-1"))).execute(_command())

    command_types = {
        command.command_type for command in uow.command_log.pending_commands
    }
    assert (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        not in command_types
    )


@pytest.mark.asyncio
async def test_run_once_no_fitting_item_creates_no_execute_command() -> None:
    uow = FakeWorkflowUnitOfWork()

    result = await _runner(uow, FakeSelector(None)).execute(_command())

    assert result.drained_count == 0
    assert uow.command_log.pending_commands == []


@pytest.mark.asyncio
async def test_run_once_completed_item_is_not_selected() -> None:
    uow = FakeWorkflowUnitOfWork()

    result = await _runner(uow, FakeSelector(None)).execute(_command())

    assert result.drained_count == 0
    assert uow.command_log.pending_commands == []


def _runner(
    uow: FakeWorkflowUnitOfWork,
    selector: FakeSelector,
) -> RunClaimBuilderCapacityQueueOnce:
    bridge = ClaimBuilderCapacityDrainBridge(
        workflow_run_id="workflow-1",
        workflow_unit_of_work=uow,
        dispatch_context_resolver=FakeContextResolver(),
        source_document_ref="source-document-1",
        active_model_ref="qwen/qwen3-32b",
        scheduled_work_item_count=1,
    )
    drain = RunCapacityWindowDrain(
        lane_claim_repository=FakeLaneClaims(),
        budget_repository=FakeBudget(),
        capacity_selector=SelectCapacityAdmissionWorkItem(selector),
        projection_lifecycle_synchronizer=FakeLifecycle(),
        strategy=bridge,
    )
    return RunClaimBuilderCapacityQueueOnce(capacity_window_drain=drain)


def _command() -> RunClaimBuilderCapacityQueueOnceCommand:
    return RunClaimBuilderCapacityQueueOnceCommand(
        workflow_run_id="workflow-1",
        provider="groq",
        model_ref="qwen/qwen3-32b",
        account_ref="account-1",
        now=_now(),
        remaining_minute_requests=60,
        remaining_minute_tokens=6000,
        remaining_daily_requests=1000,
        remaining_daily_tokens=500000,
    )


def _item(work_item_id: str) -> CapacityAdmissionSelectableWorkItem:
    return CapacityAdmissionSelectableWorkItem(
        work_item_id=work_item_id,
        lane_key=_selection_lane(),
        status=cast(Literal["retryable_failed", "ready"], "ready"),
        required_window_tokens=512,
    )
