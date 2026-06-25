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
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    HandlePrepareClaimBuilderDispatchBatchCommand,
    HandlePrepareClaimBuilderDispatchBatchCommandHandler,
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
                    "estimated_prompt_tokens": 100,
                    "estimated_completion_tokens": 10,
                    "estimated_requests": 1,
                },
                "account_capacities": (
                    {
                        "provider": "groq",
                        "account_ref": "groq-account-1",
                        "model_ref": "qwen/qwen3-32b",
                        "remaining_minute_requests": 2,
                        "remaining_minute_tokens": 7000,
                        "remaining_daily_requests": 100,
                        "remaining_daily_tokens": 50000,
                    },
                ),
                "active_model_ref": "qwen/qwen3-32b",
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _lane() -> CapacityAdmissionLaneSummary:
    return CapacityAdmissionLaneSummary(
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )


def _admission_result() -> CapacityWindowAdmissionPassResult:
    projection_event_id = UUID("00000000-0000-0000-0000-000000000201")
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
                estimated_input_tokens=100,
                estimated_output_tokens=10,
                effective_output_cap_tokens=50,
                reserved_total_tokens=150,
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
async def test_prepare_claim_builder_can_use_capacity_admission_branch() -> None:
    admission_pass = FakeCapacityWindowAdmissionPass(result=_admission_result())
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
        HandlePrepareClaimBuilderDispatchBatchCommand(
            workflow_command=_workflow_command(),
        ),
        capacity_window_admission_pass=admission_pass,
        workflow_unit_of_work=workflow_unit_of_work,
    )

    assert result.prepared_dispatch_count == 1
    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 1
    assert len(admission_pass.calls) == 1
    admission_command = admission_pass.calls[0]
    assert admission_command.workflow_run_id == _workflow_run_id()
    assert admission_command.phase == CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase
    assert admission_command.operation_key == (
        CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key
    )
    assert admission_command.lane_key.work_kind == (
        CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind
    )
    assert admission_command.lane_key.provider == "groq"
    assert admission_command.lane_key.account_ref == "groq-account-1"
    assert admission_command.lane_key.model_ref == "qwen/qwen3-32b"
    assert admission_command.budget.remaining_requests == 2
    assert admission_command.budget.remaining_tokens == 7000
    assert admission_command.budget.remaining_daily_requests == 100
    assert admission_command.budget.remaining_daily_tokens == 50000
    assert admission_command.max_admitted_items == 1

    assert workflow_unit_of_work.outbox.events[0].event_type == (
        "ClaimBuilderDispatchBatchPrepared"
    )
    execute_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        execute_command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert execute_command.payload["dispatch_attempt_id"] == "attempt-1"
    assert execute_command.payload["work_item_id"] == "work-item-1"
    assert execute_command.payload["source_unit_ref"] == "source-unit-1"
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


def test_handler_source_keeps_legacy_prepare_only_as_fallback() -> None:
    import inspect

    from src.contexts.knowledge_workbench.application.sagas import (
        handle_prepare_claim_builder_dispatch_batch_command,
    )

    source = inspect.getsource(handle_prepare_claim_builder_dispatch_batch_command)

    assert "capacity_window_admission_pass is not None" in source
    assert "prepare_llm_dispatch_batch is required when" in source
