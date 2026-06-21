from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_workflow_effects import (
    SourceIngestionNextCommandEffect,
    SourceIngestionWorkflowEffects,
    SourceIngestionWorkflowEventEffect,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
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
from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
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
class ApplySourceIngestionWorkflowEffectsCommand:
    effects: SourceIngestionWorkflowEffects

    def __post_init__(self) -> None:
        if not isinstance(self.effects, SourceIngestionWorkflowEffects):
            raise TypeError("effects must be SourceIngestionWorkflowEffects")


@dataclass(frozen=True, slots=True)
class ApplySourceIngestionWorkflowEffectsResult:
    completed_command_type: KnowledgeExtractionCanonicalCommandType
    appended_event_count: int
    appended_next_command_count: int
    saved_progress_snapshot: bool
    appended_timeline_entry_count: int
    saved_resource_usage: bool


class ApplySourceIngestionWorkflowEffects:
    async def execute(
        self,
        command: ApplySourceIngestionWorkflowEffectsCommand,
        *,
        unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> ApplySourceIngestionWorkflowEffectsResult:
        effects = command.effects
        completion_effect = effects.command_completion_effect

        completed_command = await unit_of_work.command_log.append_pending_command(
            _workflow_command_from_completion_effect(effects),
        )
        await unit_of_work.command_log.mark_command_completed(
            command_id=completed_command.command_id,
            completed_at=completion_effect.completed_at,
        )

        appended_event_count = 0
        for event_effect in effects.event_effects:
            persisted_event = await unit_of_work.outbox.append_event(
                _workflow_event_from_event_effect(
                    effects=effects,
                    event_effect=event_effect,
                )
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(persisted_event)
            appended_event_count += 1

        appended_next_command_count = 0
        for next_command_effect in effects.next_command_effects:
            await unit_of_work.command_log.append_pending_command(
                _workflow_command_from_next_command_effect(next_command_effect)
            )
            appended_next_command_count += 1

        progress_at = _source_ingestion_progress_occurred_at(effects)
        existing_progress = await unit_of_work.progress_snapshots.get_snapshot(
            effects.workflow_run_id
        )
        await unit_of_work.progress_snapshots.save_snapshot(
            _source_ingestion_progress_snapshot(
                effects=effects,
                occurred_at=progress_at,
                existing=existing_progress,
            )
        )

        appended_timeline_entry_count = 0
        for entry in _timeline_entries(effects):
            await unit_of_work.timeline.append_entry(entry)
            appended_timeline_entry_count += 1

        existing_usage = await unit_of_work.resource_usage.get_usage(
            effects.workflow_run_id
        )
        usage = existing_usage or WorkflowResourceUsageSnapshot(
            workflow_run_id=effects.workflow_run_id,
            updated_at=progress_at,
        )
        await unit_of_work.resource_usage.save_usage(
            usage.add_usage(
                request_count=0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_cost_microusd=0,
                duration_ms=0,
                provider_key=None,
                updated_at=progress_at,
            )
        )

        return ApplySourceIngestionWorkflowEffectsResult(
            completed_command_type=completion_effect.command_type,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            saved_progress_snapshot=True,
            appended_timeline_entry_count=appended_timeline_entry_count,
            saved_resource_usage=True,
        )


def _workflow_command_from_completion_effect(
    effects: SourceIngestionWorkflowEffects,
) -> WorkflowCommand:
    completion_effect = effects.command_completion_effect
    return WorkflowCommand(
        command_id=_command_id_from_idempotency_key(completion_effect.idempotency_key),
        command_type=completion_effect.command_type.value,
        workflow_run_id=completion_effect.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(completion_effect.idempotency_key),
        payload={
            "source_document_ref": effects.source_document_ref,
            "source_unit_count": effects.source_unit_count,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=completion_effect.completed_at,
        created_at=completion_effect.completed_at,
        updated_at=completion_effect.completed_at,
    )


def _workflow_command_from_next_command_effect(
    effect: SourceIngestionNextCommandEffect,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=_command_id_from_idempotency_key(effect.idempotency_key),
        command_type=effect.command_type.value,
        workflow_run_id=effect.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(effect.idempotency_key),
        payload=effect.payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=effect.run_after,
        created_at=effect.run_after,
        updated_at=effect.run_after,
    )


def _workflow_event_from_event_effect(
    *,
    effects: SourceIngestionWorkflowEffects,
    event_effect: SourceIngestionWorkflowEventEffect,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=_event_id_from_event_effect(
            effects=effects,
            event_effect=event_effect,
        ),
        event_type=event_effect.event_type.value,
        workflow_run_id=event_effect.workflow_run_id,
        payload=event_effect.payload,
        occurred_at=event_effect.occurred_at,
    )


def _command_id_from_idempotency_key(idempotency_key: str) -> WorkflowCommandId:
    return WorkflowCommandId(f"workflow-command:{idempotency_key}")


def _event_id_from_event_effect(
    *,
    effects: SourceIngestionWorkflowEffects,
    event_effect: SourceIngestionWorkflowEventEffect,
) -> WorkflowEventId:
    if (
        event_effect.event_type
        is KnowledgeExtractionCanonicalEventType.SOURCE_UNIT_CREATED
    ):
        source_unit_ref = event_effect.payload.get("source_unit_ref")
        if not isinstance(source_unit_ref, str) or not source_unit_ref.strip():
            raise ValueError("SourceUnitCreated payload requires source_unit_ref")
        return WorkflowEventId(
            "workflow-event:"
            f"{effects.workflow_run_id}:"
            f"{event_effect.event_type.value}:"
            f"{source_unit_ref}"
        )
    if (
        event_effect.event_type
        is KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED
    ):
        return WorkflowEventId(
            "workflow-event:"
            f"{effects.workflow_run_id}:"
            "SOURCE_UNITS_CREATED:"
            f"{effects.source_document_ref}:"
            "source-units"
        )

    return WorkflowEventId(
        "workflow-event:"
        f"{effects.workflow_run_id}:"
        f"{event_effect.event_type.value}:"
        f"{effects.source_document_ref}"
    )


def _source_ingestion_progress_snapshot(
    *,
    effects: SourceIngestionWorkflowEffects,
    occurred_at: datetime,
    existing: WorkflowProgressSnapshot | None,
) -> WorkflowProgressSnapshot:
    return WorkflowProgressSnapshot(
        workflow_run_id=effects.workflow_run_id,
        current_phase="SOURCE_INGESTION",
        workflow_status="RUNNING",
        total_work_items=effects.source_unit_count,
        scheduled_work_items=0,
        running_work_items=0,
        completed_work_items=effects.source_unit_count,
        deferred_work_items=0,
        retryable_failed_work_items=0,
        terminal_failed_work_items=0,
        blocked_work_items=0,
        domain_counters={"source_unit_count": effects.source_unit_count},
        started_at=existing.started_at if existing is not None else occurred_at,
        updated_at=occurred_at,
        completed_at=None,
    )


def _source_ingestion_progress_occurred_at(
    effects: SourceIngestionWorkflowEffects,
) -> datetime:
    for progress_effect in effects.progress_effects:
        if progress_effect.read_model_name.value == "progress_snapshot":
            return progress_effect.occurred_at
    return effects.command_completion_effect.completed_at


def _timeline_entries(
    effects: SourceIngestionWorkflowEffects,
) -> tuple[WorkflowTimelineEntry, ...]:
    entries: list[WorkflowTimelineEntry] = []

    entries.append(
        WorkflowTimelineEntry(
            timeline_entry_id=(
                f"workflow-timeline:{effects.workflow_run_id}:"
                "INGEST_SOURCE_DOCUMENT:completed"
            ),
            workflow_run_id=effects.workflow_run_id,
            event_type=KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT.value,
            phase="SOURCE_INGESTION",
            severity=WorkflowTimelineSeverity.INFO,
            message="Source ingestion command completed",
            payload_summary={
                "source_document_ref": effects.source_document_ref,
                "source_unit_count": effects.source_unit_count,
            },
            occurred_at=effects.command_completion_effect.completed_at,
            source_ref=effects.source_document_ref,
        )
    )

    for event_effect in effects.event_effects:
        entries.append(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{effects.workflow_run_id}:"
                    f"{event_effect.event_type.value}:"
                    f"{effects.source_document_ref}"
                ),
                workflow_run_id=effects.workflow_run_id,
                event_type=event_effect.event_type.value,
                phase="SOURCE_INGESTION",
                severity=WorkflowTimelineSeverity.INFO,
                message=_event_timeline_message(event_effect.event_type),
                payload_summary=event_effect.payload,
                occurred_at=event_effect.occurred_at,
                source_ref=effects.source_document_ref,
            )
        )

    for next_command_effect in effects.next_command_effects:
        entries.append(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{effects.workflow_run_id}:"
                    f"{next_command_effect.command_type.value}:requested"
                ),
                workflow_run_id=effects.workflow_run_id,
                event_type=next_command_effect.command_type.value,
                phase="SOURCE_INGESTION",
                severity=WorkflowTimelineSeverity.INFO,
                message=_next_command_timeline_message(
                    next_command_effect.command_type
                ),
                payload_summary=next_command_effect.payload,
                occurred_at=next_command_effect.run_after,
                source_ref=effects.source_document_ref,
            )
        )

    return tuple(entries)


def _event_timeline_message(
    event_type: KnowledgeExtractionCanonicalEventType,
) -> str:
    if event_type is KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED:
        return "Source document persisted"
    if event_type is KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED:
        return "Source units created"
    return event_type.value


def _next_command_timeline_message(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> str:
    if (
        command_type
        is KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    ):
        return "Claim builder section work scheduling requested"
    return command_type.value
