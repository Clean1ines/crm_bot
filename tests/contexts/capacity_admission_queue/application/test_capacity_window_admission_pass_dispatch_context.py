from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionPass,
    CapacityWindowAdmissionPassCommand,
    CapacityWindowAdmissionReservationResult,
    CapacityWindowAdmissionExecutionReference,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionCapacityReservationSummary,
    CapacityAdmissionLaneSummary,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    CapacityAdmissionWindowBudget,
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
    return datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return _now() + timedelta(seconds=90)


def _lane_key() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.draft_claim_compaction",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="openai/gpt-oss-120b",
    )


class FakeSelector:
    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        del lane_key, max_required_window_tokens
        return None

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        del max_required_window_tokens
        return CapacityAdmissionSelectableWorkItem(
            work_item_id="work-1",
            lane_key=lane_key,
            status="ready",
            required_window_tokens=150,
            input_tokens=100,
            artifact_tokens=10,
        )


class FakeReservation:
    async def reserve_capacity_for_selected_work_item(
        self,
        *,
        reservation_ref: str,
        attempt_id: str,
        execution_lane_key: CapacityAdmissionLaneKey,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        budget: CapacityAdmissionWindowBudget,
        now: datetime,
        expires_at: datetime,
    ) -> CapacityWindowAdmissionReservationResult:
        del attempt_id, execution_lane_key, selected_work_item, budget, now
        return CapacityWindowAdmissionReservationResult(
            reserved=True,
            budget_after=CapacityAdmissionWindowBudget(
                remaining_requests=1,
                remaining_tokens=9850,
                remaining_daily_requests=99,
                remaining_daily_tokens=999850,
            ),
            reservation_summary=CapacityAdmissionCapacityReservationSummary(
                reservation_ref=reservation_ref,
                work_item_id="work-1",
                lane=CapacityAdmissionLaneSummary(
                    work_kind="knowledge_workbench.draft_claim_compaction",
                    provider="groq",
                    account_ref="groq-account-1",
                    model_ref="openai/gpt-oss-120b",
                ),
                reserved_requests=1,
                reserved_tokens=150,
                expires_at=expires_at,
            ),
        )


class FakeExecutionLease:
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
        del now
        return LeasedWorkItemRecord(
            work_item=WorkItem(
                work_item_id=work_item_id,
                work_kind=work_kind,
                status=WorkItemStatus.LEASED,
                attempt_count=1,
                leased_by=worker,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
            ),
            schedule_payload={
                "workflow_run_id": "workflow-1",
                "group_ref": "group-1",
                "batch_ref": "batch-1",
                "round_index": 2,
                "expected_output_kind": "compacted_claims",
                "source_claim_refs": ("claim-1", "claim-2"),
                "left_node_ref": "node-left",
                "right_node_ref": "node-right",
            },
        )


class FakeProjectionAdmitter:
    async def admit_projection_work_item(
        self,
        command,
    ) -> CapacityAdmissionProjectionLeaseResult:
        return CapacityAdmissionProjectionLeaseResult(
            work_item_id=command.work_item_id,
            lane_key=command.lane_key,
            previous_status="ready",
            status="leased",
            event_id=UUID("00000000-0000-0000-0000-000000000777"),
        )


class FakeExecutionBoundary:
    async def start_or_append_execution(
        self,
        *,
        selected_work_item: CapacityAdmissionSelectableWorkItem,
        execution_lane_key: CapacityAdmissionLaneKey,
        leased_work_item: LeasedWorkItemRecord,
        projection_lease: CapacityAdmissionProjectionLeaseResult,
        capacity_reservation: CapacityAdmissionCapacityReservationSummary,
        now: datetime,
    ) -> CapacityWindowAdmissionExecutionReference:
        del (
            selected_work_item,
            execution_lane_key,
            leased_work_item,
            projection_lease,
            capacity_reservation,
            now,
        )
        return CapacityWindowAdmissionExecutionReference(
            work_item_id="work-1",
            attempt_id="attempt-1",
            attempt_number=1,
        )


class FakeActiveLeaseInspector:
    async def has_active_leased_work(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        now: datetime,
    ) -> bool:
        del lane_key, now
        return False


async def test_capacity_window_admission_pass_carries_dispatch_context_from_schedule_payload() -> (
    None
):
    result = await CapacityWindowAdmissionPass(
        selector=FakeSelector(),
        execution_lease_repository=FakeExecutionLease(),
        projection_admitter=FakeProjectionAdmitter(),
        capacity_reservation=FakeReservation(),
        execution_boundary=FakeExecutionBoundary(),
        active_lease_inspector=FakeActiveLeaseInspector(),
    ).execute(
        CapacityWindowAdmissionPassCommand(
            workflow_run_id="workflow-1",
            phase="draft_claim_compaction",
            operation_key="prepare_draft_claim_compaction_dispatch",
            lane_key=_lane_key(),
            execution_lane_key=_lane_key(),
            budget=CapacityAdmissionWindowBudget(
                remaining_requests=2,
                remaining_tokens=10000,
                remaining_daily_requests=100,
                remaining_daily_tokens=1000000,
            ),
            worker=WorkerRef("worker-1"),
            lease_token_prefix="lease-prefix",
            lease_expires_at=_lease_expires_at(),
            now=_now(),
            max_admitted_items=1,
        )
    )

    dispatch_context = result.admitted_items[0].dispatch_context
    assert dispatch_context is not None
    assert dispatch_context.group_ref == "group-1"
    assert dispatch_context.batch_ref == "batch-1"
    assert dispatch_context.round_index == 2
    assert dispatch_context.expected_output_kind == "compacted_claims"
    assert dispatch_context.input_claim_refs == ("claim-1", "claim-2")
    assert dispatch_context.input_node_refs == ("node-left", "node-right")
