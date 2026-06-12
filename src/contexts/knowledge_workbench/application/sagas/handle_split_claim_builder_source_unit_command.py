from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_split_supersede_repository_port import (
    WorkItemSplitSupersedeRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.supersede_waiting_work_items_for_split import (
    SupersedeWaitingWorkItemsForSplit,
    SupersedeWaitingWorkItemsForSplitCommand,
)
from src.contexts.knowledge_workbench.application.sagas.create_source_units_for_ingestion import (
    build_source_units_from_text,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.schedule_claim_builder_section_work import (
    ScheduleClaimBuilderSectionWork,
    ScheduleClaimBuilderSectionWorkCommand,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
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
class HandleSplitClaimBuilderSourceUnitCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleSplitClaimBuilderSourceUnitResult:
    workflow_run_id: str
    parent_source_unit_ref: str
    child_source_unit_count: int
    superseded_work_item_count: int
    scheduled_child_work_item_count: int
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.parent_source_unit_ref, "parent_source_unit_ref")
        for field_name, value in (
            ("child_source_unit_count", self.child_source_unit_count),
            ("superseded_work_item_count", self.superseded_work_item_count),
            ("scheduled_child_work_item_count", self.scheduled_child_work_item_count),
            ("appended_event_count", self.appended_event_count),
            ("appended_next_command_count", self.appended_next_command_count),
        ):
            _require_non_negative_int(value, field_name)
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandleSplitClaimBuilderSourceUnitCommandHandler:
    async def execute(
        self,
        command: HandleSplitClaimBuilderSourceUnitCommand,
        *,
        source_management_repository: SourceManagementRepositoryPort,
        work_item_scheduling_repository: WorkItemSchedulingRepositoryPort,
        work_item_split_supersede_repository: WorkItemSplitSupersedeRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleSplitClaimBuilderSourceUnitResult:
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
        source_unit_refs = _payload_text_tuple(payload, "source_unit_refs")
        if len(source_unit_refs) != 1:
            raise ValueError(
                "SPLIT_CLAIM_BUILDER_SOURCE_UNIT supports exactly one source_unit_ref"
            )
        affected_work_item_refs = _payload_text_tuple(
            payload, "affected_work_item_refs"
        )
        occurred_at = workflow_command.updated_at

        parent_source_unit_ref = SourceUnitRef(source_unit_refs[0])
        parent_source_unit = await source_management_repository.load_source_unit(
            parent_source_unit_ref,
        )
        if parent_source_unit is None:
            raise ValueError("parent source unit not found")
        if parent_source_unit.document_ref != source_document_ref:
            raise ValueError("parent source unit document_ref mismatch")

        source_document = await source_management_repository.load_source_document(
            source_document_ref,
        )
        if source_document is None:
            raise ValueError("source document not found")

        existing_source_units = (
            await source_management_repository.list_source_units_for_document(
                source_document_ref,
            )
        )
        child_source_units = _split_parent_source_unit(
            source_document=source_document,
            parent_source_unit=parent_source_unit,
            existing_source_units=existing_source_units,
            occurred_at=occurred_at,
        )

        await source_management_repository.save_source_units(child_source_units)

        supersede_result = await SupersedeWaitingWorkItemsForSplit(
            repository=work_item_split_supersede_repository,
        ).execute(
            SupersedeWaitingWorkItemsForSplitCommand(
                work_item_ids=affected_work_item_refs,
            )
        )

        scheduling_result = await ScheduleClaimBuilderSectionWork(
            scheduling_repository=work_item_scheduling_repository,
        ).execute(
            ScheduleClaimBuilderSectionWorkCommand(
                workflow_run_id=workflow_run_id,
                source_document_ref=source_document_ref,
                source_units=child_source_units,
            )
        )
        if scheduling_result.conflict_count > 0:
            raise ValueError("claim builder child work scheduling conflict")

        scheduled_child_work_item_count = (
            scheduling_result.created_count + scheduling_result.already_exists_count
        )

        completed_event = _source_unit_split_completed_event(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            source_document_ref=source_document_ref,
            parent_source_unit_ref=parent_source_unit_ref,
            child_source_units=child_source_units,
            superseded_work_item_refs=supersede_result.superseded_work_item_ids,
            scheduled_child_work_item_count=scheduled_child_work_item_count,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.outbox.append_event(completed_event)

        next_command = _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            source_document_ref=source_document_ref,
            parent_source_unit_ref=parent_source_unit_ref,
            scheduled_child_work_item_count=scheduled_child_work_item_count,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.command_log.append_pending_command(next_command)

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            child_source_unit_count=len(child_source_units),
            superseded_work_item_count=len(supersede_result.superseded_work_item_ids),
            scheduled_child_work_item_count=scheduled_child_work_item_count,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                completed_event=completed_event,
                child_source_unit_count=len(child_source_units),
                superseded_work_item_count=len(
                    supersede_result.superseded_work_item_ids
                ),
                scheduled_child_work_item_count=scheduled_child_work_item_count,
                occurred_at=occurred_at,
            )
        )

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandleSplitClaimBuilderSourceUnitResult(
            workflow_run_id=workflow_run_id,
            parent_source_unit_ref=parent_source_unit_ref.value,
            child_source_unit_count=len(child_source_units),
            superseded_work_item_count=len(supersede_result.superseded_work_item_ids),
            scheduled_child_work_item_count=scheduled_child_work_item_count,
            appended_event_count=1,
            appended_next_command_count=1,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT.value
    ):
        raise ValueError(
            "workflow_command command_type must be SplitClaimBuilderSourceUnit"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _split_parent_source_unit(
    *,
    source_document: SourceDocument,
    parent_source_unit: SourceUnit,
    existing_source_units: tuple[SourceUnit, ...],
    occurred_at: datetime,
) -> tuple[SourceUnit, ...]:
    max_existing_ordinal = max(
        (source_unit.ordinal for source_unit in existing_source_units),
        default=-1,
    )
    candidate_units = build_source_units_from_text(
        document=source_document,
        raw_text=parent_source_unit.text.value,
        occurred_at=occurred_at,
    )
    if len(candidate_units) < 2:
        raise ValueError("source unit split produced fewer than two child source units")

    child_units: list[SourceUnit] = []
    for offset, candidate in enumerate(candidate_units, start=1):
        child_ordinal = max_existing_ordinal + offset
        child_units.append(
            SourceUnit(
                unit_ref=_child_source_unit_ref(
                    parent_source_unit=parent_source_unit,
                    candidate_source_unit=candidate,
                    child_ordinal=child_ordinal,
                ),
                document_ref=parent_source_unit.document_ref,
                unit_kind=candidate.unit_kind,
                text=candidate.text,
                heading_path=candidate.heading_path,
                lineage=SourceUnitLineage(parent_refs=(parent_source_unit.unit_ref,)),
                ordinal=child_ordinal,
                created_at=occurred_at,
            )
        )
    return tuple(child_units)


def _child_source_unit_ref(
    *,
    parent_source_unit: SourceUnit,
    candidate_source_unit: SourceUnit,
    child_ordinal: int,
) -> SourceUnitRef:
    child_hash = sha256(
        (
            f"{parent_source_unit.unit_ref.value}:"
            f"{candidate_source_unit.unit_ref.value}:"
            f"{child_ordinal}:"
            f"{candidate_source_unit.text.value}"
        ).encode("utf-8"),
    ).hexdigest()
    return SourceUnitRef(
        value=(
            f"source-unit:{parent_source_unit.document_ref.value}:"
            f"split:{child_ordinal}:{child_hash}"
        )
    )


def _source_unit_split_completed_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    source_document_ref: SourceDocumentRef,
    parent_source_unit_ref: SourceUnitRef,
    child_source_units: tuple[SourceUnit, ...],
    superseded_work_item_refs: tuple[str, ...],
    scheduled_child_work_item_count: int,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_COMPLETED.value}:"
            f"{parent_source_unit_ref.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_COMPLETED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "source_document_ref": source_document_ref.value,
            "parent_source_unit_ref": parent_source_unit_ref.value,
            "child_source_unit_refs": tuple(
                source_unit.unit_ref.value for source_unit in child_source_units
            ),
            "superseded_work_item_refs": superseded_work_item_refs,
            "scheduled_child_work_item_count": scheduled_child_work_item_count,
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _prepare_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    source_document_ref: SourceDocumentRef,
    parent_source_unit_ref: SourceUnitRef,
    scheduled_child_work_item_count: int,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        "prepare-claim-builder-dispatch-batch-after-source-split:"
        f"{workflow_run_id}:"
        f"{parent_source_unit_ref.value}"
    )
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "source_document_ref": source_document_ref.value,
        "parent_source_unit_ref": parent_source_unit_ref.value,
        "scheduled_work_item_count": scheduled_child_work_item_count,
    }

    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if dispatch_preparation is not None:
        if not isinstance(dispatch_preparation, Mapping):
            raise ValueError("llm_dispatch_preparation must be mapping")
        payload["llm_dispatch_preparation"] = dict(dispatch_preparation)

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    child_source_unit_count: int,
    superseded_work_item_count: int,
    scheduled_child_work_item_count: int,
    occurred_at: datetime,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    counters = dict(existing.domain_counters) if existing is not None else {}
    counters["claim_builder_source_unit_split_completed_count"] = (
        counters.get("claim_builder_source_unit_split_completed_count", 0) + 1
    )
    counters["claim_builder_child_source_unit_count"] = (
        counters.get("claim_builder_child_source_unit_count", 0)
        + child_source_unit_count
    )
    counters["claim_builder_split_superseded_work_item_count"] = (
        counters.get("claim_builder_split_superseded_work_item_count", 0)
        + superseded_work_item_count
    )
    counters["claim_builder_split_child_work_item_count"] = (
        counters.get("claim_builder_split_child_work_item_count", 0)
        + scheduled_child_work_item_count
    )

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
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
            domain_counters=counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    completed_event: WorkflowEvent,
    child_source_unit_count: int,
    superseded_work_item_count: int,
    scheduled_child_work_item_count: int,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    parent_source_unit_ref = completed_event.payload.get("parent_source_unit_ref")
    if (
        not isinstance(parent_source_unit_ref, str)
        or not parent_source_unit_ref.strip()
    ):
        raise ValueError("completed event payload parent_source_unit_ref must be text")

    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_command.workflow_run_id}:"
            "ClaimBuilderSourceUnitSplitCompleted:"
            f"{parent_source_unit_ref}"
        ),
        workflow_run_id=workflow_command.workflow_run_id,
        event_type=completed_event.event_type,
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=WorkflowTimelineSeverity.INFO,
        message="Claim builder source unit split completed",
        payload_summary={
            "child_source_unit_count": child_source_unit_count,
            "superseded_work_item_count": superseded_work_item_count,
            "scheduled_child_work_item_count": scheduled_child_work_item_count,
        },
        occurred_at=occurred_at,
        source_ref=parent_source_unit_ref,
    )


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload {key} must be non-empty text")
    return value


def _payload_text_tuple(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, tuple):
        raise ValueError(f"workflow command payload {key} must be tuple")
    if not value:
        raise ValueError(f"workflow command payload {key} must be non-empty")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"workflow command payload {key} must contain non-empty text"
            )
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
