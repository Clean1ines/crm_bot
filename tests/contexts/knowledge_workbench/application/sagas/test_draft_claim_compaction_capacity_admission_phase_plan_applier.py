from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import pytest

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
from src.contexts.knowledge_workbench.application.sagas.draft_claim_compaction_capacity_admission_phase_mapper import (
    DraftClaimCompactionCapacityAdmissionPhaseMapper,
)
from src.contexts.knowledge_workbench.application.sagas.draft_claim_compaction_capacity_admission_phase_plan_applier import (
    ApplyDraftClaimCompactionCapacityAdmissionPhasePlanCommand,
    DraftClaimCompactionCapacityAdmissionPhasePlanApplier,
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


def _workflow_command(
    *,
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
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
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="openai/gpt-oss-120b",
    )


def _dispatch_context() -> CapacityAdmissionDispatchContextSummary:
    return CapacityAdmissionDispatchContextSummary(
        group_ref="group-1",
        batch_ref="batch-1",
        round_index=3,
        expected_output_kind="compacted_claims",
        input_node_refs=("node-1", "node-2"),
        input_claim_refs=("claim-1", "claim-2"),
    )


def _admitted_result() -> CapacityWindowAdmissionPassResult:
    projection_event_id = UUID("00000000-0000-0000-0000-000000000301")
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
                input_tokens=100,
                artifact_tokens=10,
                required_window_tokens=150,
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


def _skipped_result(
    reason: CapacityWindowAdmissionSkippedReason,
    *,
    frontend_event_kind: str = "capacity_admission_pass_skipped",
) -> CapacityWindowAdmissionPassResult:
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        skipped_reason=reason,
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind=frontend_event_kind,
            workflow_run_id=_workflow_run_id(),
            phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
            operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=0,
            started_attempt_count=0,
            skipped_reason=reason,
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_SKIPPED,
    )


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
        return _workflow_command(status=WorkflowCommandStatus.COMPLETED)


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


async def _apply(
    admission_result: CapacityWindowAdmissionPassResult,
) -> tuple[FakeWorkflowRuntimeUnitOfWork, int, int]:
    plan = (
        await DraftClaimCompactionCapacityAdmissionPhaseMapper().map_admission_result(
            admission_result=admission_result,
            occurred_at=_now(),
        )
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await DraftClaimCompactionCapacityAdmissionPhasePlanApplier().execute(
        ApplyDraftClaimCompactionCapacityAdmissionPhasePlanCommand(
            workflow_command=_workflow_command(),
            mapping_plan=plan,
        ),
        workflow_unit_of_work=workflow_unit_of_work,
    )
    return (
        workflow_unit_of_work,
        result.appended_event_count,
        result.appended_next_command_count,
    )


@pytest.mark.asyncio
async def test_applies_admitted_draft_claim_compaction_phase_plan() -> None:
    workflow_unit_of_work, event_count, command_count = await _apply(_admitted_result())

    assert event_count == 1
    assert command_count == 1
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "DraftClaimCompactionDispatchBatchPrepared"
    )
    assert workflow_unit_of_work.outbox.events[0].payload["dispatch_contexts"] == (
        {
            "work_item_id": "work-item-1",
            "group_ref": "group-1",
            "batch_ref": "batch-1",
            "round_index": 3,
            "expected_output_kind": "compacted_claims",
            "source_node_refs": ("node-1", "node-2"),
            "source_claim_refs": ("claim-1", "claim-2"),
        },
    )

    command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
    )
    assert command.payload["dispatch_attempt_id"] == "attempt-1"
    assert command.payload["work_item_id"] == "work-item-1"
    assert command.payload["group_ref"] == "group-1"
    assert command.payload["batch_ref"] == "batch-1"
    assert command.payload["round_index"] == 3
    assert command.payload["expected_output_kind"] == "compacted_claims"
    assert command.payload["source_node_refs"] == ("node-1", "node-2")
    assert command.payload["source_claim_refs"] == ("claim-1", "claim-2")
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert (
        workflow_unit_of_work.progress_snapshots.snapshot.domain_counters[
            "draft_claim_compaction_prepared_dispatch_count"
        ]
        == 1
    )
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


@pytest.mark.asyncio
async def test_applies_compaction_user_model_choice_without_execute_commands() -> None:
    workflow_unit_of_work, event_count, command_count = await _apply(
        _skipped_result(
            CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED,
            frontend_event_kind="capacity_admission_user_model_choice_required",
        )
    )

    assert event_count == 1
    assert command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "DraftClaimCompactionUserModelChoiceRequired"
    )
    assert workflow_unit_of_work.outbox.events[0].payload["reason"] == (
        "primary_model_daily_capacity_exhausted"
    )
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert (
        workflow_unit_of_work.progress_snapshots.snapshot.domain_counters[
            "draft_claim_compaction_user_model_choice_required_count"
        ]
        == 1
    )


@pytest.mark.asyncio
async def test_applies_compaction_capacity_waiting_without_execute_commands() -> None:
    workflow_unit_of_work, event_count, command_count = await _apply(
        _skipped_result(CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED)
    )

    assert event_count == 1
    assert command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "DraftClaimCompactionCapacityWaiting"
    )
    assert workflow_unit_of_work.outbox.events[0].payload["skipped_reason"] == (
        "capacity_exhausted"
    )
