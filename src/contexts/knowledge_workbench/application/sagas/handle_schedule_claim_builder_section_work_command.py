from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.schedule_claim_builder_section_work import (
    ScheduleClaimBuilderSectionWork,
    ScheduleClaimBuilderSectionWorkCommand,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


@dataclass(frozen=True, slots=True)
class HandleScheduleClaimBuilderSectionWorkCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleScheduleClaimBuilderSectionWorkResult:
    workflow_run_id: str
    scheduled_work_item_count: int
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        for field_name, value in (
            ("scheduled_work_item_count", self.scheduled_work_item_count),
            ("appended_event_count", self.appended_event_count),
            ("appended_next_command_count", self.appended_next_command_count),
        ):
            _require_non_negative_int(value, field_name)
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


@dataclass(frozen=True, slots=True)
class HandleScheduleClaimBuilderSectionWorkCommandHandler:
    async def execute(
        self,
        command: HandleScheduleClaimBuilderSectionWorkCommand,
        *,
        source_unit_repository: SourceManagementRepositoryPort,
        knowledge_unit_of_work: WorkItemSchedulingRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> HandleScheduleClaimBuilderSectionWorkResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)

        payload = workflow_command.payload
        workflow_run_id = _payload_text(
            payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")
        source_document_ref = SourceDocumentRef(
            _payload_text(payload, "source_document_ref")
        )
        occurred_at = workflow_command.updated_at

        source_units = await source_unit_repository.list_source_units_for_document(
            source_document_ref,
        )

        scheduling_result = await ScheduleClaimBuilderSectionWork(
            scheduling_repository=knowledge_unit_of_work,
        ).execute(
            ScheduleClaimBuilderSectionWorkCommand(
                workflow_run_id=workflow_run_id,
                source_document_ref=source_document_ref,
                source_units=source_units,
            )
        )
        if scheduling_result.conflict_count > 0:
            raise ValueError("claim builder section work scheduling conflict")

        scheduled_work_item_count = (
            scheduling_result.created_count + scheduling_result.already_exists_count
        )
        scheduled_event = _claim_builder_work_scheduled_event(
            workflow_run_id=workflow_run_id,
            source_document_ref=source_document_ref,
            scheduled_work_item_count=scheduled_work_item_count,
            occurred_at=occurred_at,
        )
        persisted_scheduled_event = await workflow_unit_of_work.outbox.append_event(
            scheduled_event
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(persisted_scheduled_event)

        next_command = _prepare_dispatch_batch_command(
            workflow_run_id=workflow_run_id,
            source_document_ref=source_document_ref,
            scheduled_work_item_count=scheduled_work_item_count,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.command_log.append_pending_command(next_command)

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            scheduled_work_item_count=scheduled_work_item_count,
            occurred_at=occurred_at,
        )

        for timeline_entry in _timeline_entries(
            workflow_command=workflow_command,
            scheduled_event=scheduled_event,
            next_command=next_command,
            source_document_ref=source_document_ref,
            scheduled_work_item_count=scheduled_work_item_count,
            occurred_at=occurred_at,
        ):
            await workflow_unit_of_work.timeline.append_entry(timeline_entry)

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandleScheduleClaimBuilderSectionWorkResult(
            workflow_run_id=workflow_run_id,
            scheduled_work_item_count=scheduled_work_item_count,
            appended_event_count=1,
            appended_next_command_count=1,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK.value
    ):
        raise ValueError(
            "workflow_command command_type must be ScheduleClaimBuilderSectionWork"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _claim_builder_work_scheduled_event(
    *,
    workflow_run_id: str,
    source_document_ref: SourceDocumentRef,
    scheduled_work_item_count: int,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_WORK_SCHEDULED.value}:"
            f"{source_document_ref.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_WORK_SCHEDULED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "source_document_ref": source_document_ref.value,
            "scheduled_work_item_count": scheduled_work_item_count,
        },
        occurred_at=occurred_at,
    )


def _prepare_dispatch_batch_command(
    *,
    workflow_run_id: str,
    source_document_ref: SourceDocumentRef,
    scheduled_work_item_count: int,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = f"prepare-claim-builder-dispatch-batch:{workflow_run_id}"
    command_payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "source_document_ref": source_document_ref.value,
        "scheduled_work_item_count": scheduled_work_item_count,
    }
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=command_payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    existing_domain_counters = (
        dict(existing.domain_counters) if existing is not None else {}
    )
    existing_domain_counters["scheduled_work_item_count"] = scheduled_work_item_count

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="CLAIM_BUILDER_WORK_SCHEDULING",
            workflow_status="RUNNING",
            total_work_items=max(
                existing.total_work_items if existing is not None else 0,
                scheduled_work_item_count,
            ),
            scheduled_work_items=scheduled_work_item_count,
            running_work_items=existing.running_work_items
            if existing is not None
            else 0,
            completed_work_items=(
                existing.completed_work_items if existing is not None else 0
            ),
            deferred_work_items=(
                existing.deferred_work_items if existing is not None else 0
            ),
            retryable_failed_work_items=(
                existing.retryable_failed_work_items if existing is not None else 0
            ),
            terminal_failed_work_items=(
                existing.terminal_failed_work_items if existing is not None else 0
            ),
            blocked_work_items=existing.blocked_work_items
            if existing is not None
            else 0,
            domain_counters=existing_domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )


def _timeline_entries(
    *,
    workflow_command: WorkflowCommand,
    scheduled_event: WorkflowEvent,
    next_command: WorkflowCommand,
    source_document_ref: SourceDocumentRef,
    scheduled_work_item_count: int,
    occurred_at: datetime,
) -> tuple[WorkflowTimelineEntry, ...]:
    return (
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{workflow_command.workflow_run_id}:"
                "ClaimBuilderSectionWorkScheduled"
            ),
            workflow_run_id=workflow_command.workflow_run_id,
            event_type=scheduled_event.event_type,
            phase="CLAIM_BUILDER_WORK_SCHEDULING",
            severity=WorkflowTimelineSeverity.INFO,
            message="Claim builder section work scheduled",
            payload_summary=scheduled_event.payload,
            occurred_at=occurred_at,
            source_ref=source_document_ref.value,
        ),
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{workflow_command.workflow_run_id}:"
                "PrepareClaimBuilderDispatchBatch:requested"
            ),
            workflow_run_id=workflow_command.workflow_run_id,
            event_type=next_command.command_type,
            phase="CLAIM_BUILDER_WORK_SCHEDULING",
            severity=WorkflowTimelineSeverity.INFO,
            message="Prepare claim builder dispatch batch requested",
            payload_summary=next_command.payload,
            occurred_at=occurred_at,
            source_ref=source_document_ref.value,
        ),
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{workflow_command.workflow_run_id}:"
                "ScheduleClaimBuilderSectionWork:completed"
            ),
            workflow_run_id=workflow_command.workflow_run_id,
            event_type=workflow_command.command_type,
            phase="CLAIM_BUILDER_WORK_SCHEDULING",
            severity=WorkflowTimelineSeverity.INFO,
            message="Schedule claim builder section work command completed",
            payload_summary={
                "workflow_run_id": workflow_command.workflow_run_id,
                "source_document_ref": source_document_ref.value,
                "scheduled_work_item_count": scheduled_work_item_count,
            },
            occurred_at=occurred_at,
            source_ref=source_document_ref.value,
        ),
    )


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
