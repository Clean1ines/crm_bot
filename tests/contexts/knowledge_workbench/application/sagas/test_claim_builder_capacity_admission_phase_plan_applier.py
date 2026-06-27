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
    CapacityAdmissionSafePreflightSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    CapacityAdmissionPhaseMappingDecision,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_admission_phase_mapper import (
    ClaimBuilderCapacityAdmissionPhaseMapper,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_capacity_admission_phase_plan_applier import (
    ApplyClaimBuilderCapacityAdmissionPhasePlanCommand,
    ClaimBuilderCapacityAdmissionPhasePlanApplier,
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


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _workflow_command(
    *,
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:prepare-claim-builder-dispatch-batch:workflow-1"
        ),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            "prepare-claim-builder-dispatch-batch:workflow-1"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": "source-document-1",
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": {
                "profile": {
                    "profile_id": "faq_claim_observations",
                    "input_tokens": 100,
                    "artifact_tokens": 10,
                    "request_count": 1,
                },
                "active_model_ref": "qwen/qwen3-32b",
            },
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _admitted_result() -> CapacityWindowAdmissionPassResult:
    projection_event_id = UUID("00000000-0000-0000-0000-000000000101")
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-item-1",
                lane=_lane(),
                selection_kind="fresh",
                input_tokens=100,
                artifact_tokens=10,
                required_window_tokens=150,
                dispatch_context=CapacityAdmissionDispatchContextSummary(
                    source_ref="source-document-1",
                    source_unit_ref="source-unit-1",
                ),
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
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=_lane(),
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-item-1",),
            attempt_ids=("attempt-1",),
            projection_event_ids=(projection_event_id,),
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
    )


def _skipped_result(
    reason: CapacityWindowAdmissionSkippedReason,
) -> CapacityWindowAdmissionPassResult:
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=_lane(),
        skipped_reason=reason,
        safe_preflight_summary=CapacityAdmissionSafePreflightSummary(
            decision=reason.value,
            reason="test reason",
            active_model_ref="qwen/qwen3-32b",
            source_split_required=(
                reason is CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED
            ),
            affected_work_item_refs=("work-item-1",)
            if reason is CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED
            else (),
            source_unit_refs=("source-unit-1",)
            if reason is CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED
            else (),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_skipped",
            workflow_run_id=_workflow_run_id(),
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
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
    plan = await ClaimBuilderCapacityAdmissionPhaseMapper().map_admission_result(
        admission_result=admission_result,
        occurred_at=_now(),
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await ClaimBuilderCapacityAdmissionPhasePlanApplier().execute(
        ApplyClaimBuilderCapacityAdmissionPhasePlanCommand(
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
async def test_applies_admitted_claim_builder_phase_plan() -> None:
    workflow_unit_of_work, event_count, command_count = await _apply(_admitted_result())

    assert event_count == 1
    assert command_count == 1
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "ClaimBuilderDispatchBatchPrepared"
    )
    command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert command.payload["dispatch_attempt_id"] == "attempt-1"
    assert command.payload["work_item_id"] == "work-item-1"
    assert command.payload["source_unit_ref"] == "source-unit-1"
    assert command.payload["claim_builder_prepare_command_id"] == (
        _workflow_command().command_id.value
    )
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert (
        workflow_unit_of_work.progress_snapshots.snapshot.domain_counters[
            "prepared_dispatch_count"
        ]
        == 1
    )
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


@pytest.mark.asyncio
async def test_applies_capacity_waiting_without_execute_commands() -> None:
    workflow_unit_of_work, event_count, command_count = await _apply(
        _skipped_result(CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED)
    )

    assert event_count == 1
    assert command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.outbox.events[0].payload["skipped_reason"] == (
        "capacity_exhausted"
    )
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert workflow_unit_of_work.timeline.entries[0].payload_summary["decision"] == (
        CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING.value
    )


@pytest.mark.asyncio
async def test_applies_source_split_required_summary_without_execute_commands() -> None:
    workflow_unit_of_work, event_count, command_count = await _apply(
        _skipped_result(CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED)
    )

    assert event_count == 1
    assert command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    event_payload = workflow_unit_of_work.outbox.events[0].payload
    assert event_payload["source_split_required"] is True
    assert event_payload["source_unit_refs"] == ("source-unit-1",)
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert (
        workflow_unit_of_work.progress_snapshots.snapshot.domain_counters[
            "claim_builder_source_split_required_count"
        ]
        == 1
    )
