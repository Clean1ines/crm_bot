from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionPassCommand,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionAdmittedItemSummary,
    CapacityAdmissionDispatchContextSummary,
    CapacityAdmissionFrontendEventSummary,
    CapacityAdmissionLaneSummary,
    CapacityAdmissionProjectionLeaseSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    HandlePrepareDraftClaimCompactionDispatchBatchCommand,
    HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:prepare-draft-claim-compaction-dispatch-batch:workflow-1"
        ),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            "prepare-draft-claim-compaction-dispatch-batch:workflow-1"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": {
                "profile": {
                    "profile_id": "draft_claim_compaction",
                    "estimated_input_tokens": 100,
                    "estimated_output_tokens": 10,
                    "estimated_requests": 1,
                },
                "account_capacities": (
                    {
                        "provider": "groq",
                        "account_ref": "groq-account-1",
                        "model_ref": "openai/gpt-oss-120b",
                        "remaining_minute_requests": 2,
                        "remaining_minute_tokens": 7000,
                        "remaining_daily_requests": 100,
                        "remaining_daily_tokens": 50000,
                    },
                ),
                "active_model_ref": "openai/gpt-oss-120b",
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref=None,
        model_ref="openai/gpt-oss-120b",
    )


def _dispatch_context() -> CapacityAdmissionDispatchContextSummary:
    return CapacityAdmissionDispatchContextSummary(
        group_ref="group-1",
        batch_ref="batch-1",
        round_index=2,
        expected_output_kind="compacted_claims",
        input_node_refs=("node-1", "node-2"),
        input_claim_refs=("claim-1", "claim-2"),
    )


def _admission_result() -> CapacityWindowAdmissionPassResult:
    projection_event_id = UUID("00000000-0000-0000-0000-000000000401")
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                selection_kind="fresh",
                estimated_input_tokens=100,
                estimated_output_tokens=10,
                effective_output_cap_tokens=50,
                reserved_total_tokens=150,
                dispatch_context=_dispatch_context(),
            ),
        ),
        projection_leases=(
            CapacityAdmissionProjectionLeaseSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                previous_status="ready",
                status="leased",
                event_id=projection_event_id,
            ),
        ),
        started_attempts=(
            CapacityAdmissionStartedAttemptSummary(
                work_item_id="work-item-1",
                attempt_id="attempt-1",
                attempt_number=1,
            ),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_completed",
            workflow_run_id=_workflow_run_id(),
            phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
            operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-item-1",),
            attempt_ids=("attempt-1",),
            projection_event_ids=(projection_event_id,),
            dispatch_contexts=(_dispatch_context(),),
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
    )


def _user_model_choice_result() -> CapacityWindowAdmissionPassResult:
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_user_model_choice_required",
            workflow_run_id=_workflow_run_id(),
            phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
            operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=0,
            started_attempt_count=0,
            skipped_reason=CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )


@dataclass(slots=True)
class FakeCapacityWindowAdmissionPass:
    result: CapacityWindowAdmissionPassResult
    calls: list[CapacityWindowAdmissionPassCommand] = field(default_factory=list)

    async def execute(self, command: CapacityWindowAdmissionPassCommand) -> object:
        self.calls.append(command)
        return self.result


@dataclass(slots=True)
class FakeCommandLogRepository:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed_command_ids.append(command_id)
        return _workflow_command()


@dataclass(slots=True)
class FakeOutboxRepository:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeProgressSnapshotRepository:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None:
        if (
            self.snapshot is not None
            and self.snapshot.workflow_run_id == workflow_run_id
        ):
            return self.snapshot
        return None

    async def save_snapshot(
        self,
        snapshot: WorkflowProgressSnapshot,
    ) -> WorkflowProgressSnapshot:
        self.snapshot = snapshot
        return snapshot


@dataclass(slots=True)
class FakeTimelineRepository:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry:
        self.entries.append(entry)
        return entry


@dataclass(slots=True)
class FakeResourceUsageRepository:
    usage: WorkflowResourceUsageSnapshot | None = None


@dataclass(slots=True)
class FakeWorkflowRuntimeUnitOfWork:
    command_log: FakeCommandLogRepository = field(
        default_factory=FakeCommandLogRepository
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository
    )


@pytest.mark.asyncio
async def test_prepare_draft_claim_compaction_can_use_capacity_admission_branch() -> (
    None
):
    admission_pass = FakeCapacityWindowAdmissionPass(result=_admission_result())
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = (
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_workflow_command(),
            ),
            capacity_window_admission_pass=admission_pass,
            workflow_unit_of_work=workflow_unit_of_work,
        )
    )

    assert result.prepared_dispatch_count == 1
    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 1
    assert len(admission_pass.calls) == 1
    admission_command = admission_pass.calls[0]
    assert admission_command.workflow_run_id == _workflow_run_id()
    assert (
        admission_command.phase == DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase
    )
    assert admission_command.operation_key == (
        DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key
    )
    assert admission_command.lane_key.work_kind == (
        DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind
    )
    assert admission_command.lane_key.provider == "groq"
    assert admission_command.lane_key.account_ref is None
    assert admission_command.lane_key.model_ref == "openai/gpt-oss-120b"
    assert admission_command.execution_lane_key.provider == "groq"
    assert admission_command.execution_lane_key.account_ref == "groq-account-1"
    assert admission_command.execution_lane_key.model_ref == "openai/gpt-oss-120b"
    assert admission_command.budget.remaining_requests == 2
    assert admission_command.budget.remaining_tokens == 7000
    assert admission_command.budget.remaining_daily_requests == 100
    assert admission_command.budget.remaining_daily_tokens == 50000
    assert admission_command.max_admitted_items == 1

    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "DraftClaimCompactionDispatchBatchPrepared"
    )
    execute_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        execute_command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
    )
    assert execute_command.payload["dispatch_attempt_id"] == "attempt-1"
    assert execute_command.payload["work_item_id"] == "work-item-1"
    assert execute_command.payload["group_ref"] == "group-1"
    assert execute_command.payload["batch_ref"] == "batch-1"
    assert execute_command.payload["round_index"] == 2
    assert execute_command.payload["expected_output_kind"] == "compacted_claims"
    assert execute_command.payload["source_node_refs"] == ("node-1", "node-2")
    assert execute_command.payload["source_claim_refs"] == ("claim-1", "claim-2")
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


@pytest.mark.asyncio
async def test_prepare_draft_claim_compaction_admission_branch_can_request_user_model_choice() -> (
    None
):
    admission_pass = FakeCapacityWindowAdmissionPass(result=_user_model_choice_result())
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = (
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_workflow_command(),
            ),
            capacity_window_admission_pass=admission_pass,
            workflow_unit_of_work=workflow_unit_of_work,
        )
    )

    assert result.prepared_dispatch_count == 0
    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "DraftClaimCompactionUserModelChoiceRequired"
    )
    assert workflow_unit_of_work.outbox.events[0].payload["reason"] == (
        "primary_model_daily_capacity_exhausted"
    )
