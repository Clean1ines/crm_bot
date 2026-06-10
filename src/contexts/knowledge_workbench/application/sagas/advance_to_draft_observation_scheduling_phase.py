from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_checkpoints import (
    replace_or_append_checkpoint,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.schedule_draft_observation_extraction_work import (
    ScheduleDraftObservationExtractionWork,
    ScheduleDraftObservationExtractionWorkCommand,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)


@dataclass(frozen=True, slots=True)
class AdvanceToDraftObservationSchedulingPhaseCommand:
    state: KnowledgeExtractionWorkflowState
    source_units: tuple[SourceUnit, ...]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.state, KnowledgeExtractionWorkflowState):
            raise TypeError("state must be KnowledgeExtractionWorkflowState")
        if not isinstance(self.source_units, tuple):
            raise TypeError("source_units must be tuple")
        for source_unit in self.source_units:
            if not isinstance(source_unit, SourceUnit):
                raise TypeError("source_units must contain only SourceUnit")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")

        if (
            self.state.current_phase
            is not KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
        ):
            raise ValueError("workflow current_phase must be SOURCE_UNITS_CREATED")
        if self.state.status is not KnowledgeExtractionWorkflowStatus.RUNNING:
            raise ValueError("workflow status must be RUNNING")


@dataclass(frozen=True, slots=True)
class AdvanceToDraftObservationSchedulingPhaseResult:
    state: KnowledgeExtractionWorkflowState
    checkpoint: KnowledgeExtractionPhaseCheckpoint
    planned_count: int
    created_count: int
    already_exists_count: int
    conflict_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.state, KnowledgeExtractionWorkflowState):
            raise TypeError("state must be KnowledgeExtractionWorkflowState")
        if not isinstance(self.checkpoint, KnowledgeExtractionPhaseCheckpoint):
            raise TypeError("checkpoint must be KnowledgeExtractionPhaseCheckpoint")

        for field_name, value in (
            ("planned_count", self.planned_count),
            ("created_count", self.created_count),
            ("already_exists_count", self.already_exists_count),
            ("conflict_count", self.conflict_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")

        if (
            self.checkpoint.phase_key
            is not KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
        ):
            raise ValueError("checkpoint phase_key must be PROMPT_A_WORK_SCHEDULED")
        if (
            self.state.current_phase
            is not KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
        ):
            raise ValueError("state current_phase must be PROMPT_A_WORK_SCHEDULED")


@dataclass(frozen=True, slots=True)
class AdvanceToDraftObservationSchedulingPhase:
    scheduling_service: ScheduleDraftObservationExtractionWork

    async def execute(
        self,
        command: AdvanceToDraftObservationSchedulingPhaseCommand,
    ) -> AdvanceToDraftObservationSchedulingPhaseResult:
        state = command.state
        source_units = command.source_units

        scheduling_result = await self.scheduling_service.execute(
            ScheduleDraftObservationExtractionWorkCommand(
                workflow_run_id=state.workflow_run_id,
                source_document_ref=SourceDocumentRef(state.source_document_ref),
                source_units=source_units,
            ),
        )
        if scheduling_result.conflict_count > 0:
            raise ValueError("draft observation scheduling conflict")

        checkpoint = KnowledgeExtractionPhaseCheckpoint(
            workflow_run_id=state.workflow_run_id,
            phase_key=KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED,
            phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
            expected_count=scheduling_result.planned_count,
            completed_count=(
                scheduling_result.created_count + scheduling_result.already_exists_count
            ),
            failed_count=0,
            blocked_count=0,
            idempotency_key=f"prompt-a-work-scheduled:{state.workflow_run_id}",
            checkpoint_payload={
                "planned_count": scheduling_result.planned_count,
                "created_count": scheduling_result.created_count,
                "already_exists_count": scheduling_result.already_exists_count,
                "conflict_count": scheduling_result.conflict_count,
                "source_unit_count": len(source_units),
                "scheduler": "execution_runtime.ensure_work_items_scheduled",
                "schedule_schema_version": 1,
                "scheduled_items": [
                    item.to_checkpoint_payload()
                    for item in scheduling_result.scheduled_items
                ],
            },
            updated_at=command.occurred_at,
        )
        next_state = KnowledgeExtractionWorkflowState(
            workflow_run_id=state.workflow_run_id,
            project_id=state.project_id,
            source_document_ref=state.source_document_ref,
            status=KnowledgeExtractionWorkflowStatus.RUNNING,
            current_phase=KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED,
            checkpoints=replace_or_append_checkpoint(
                state.checkpoints,
                checkpoint,
            ),
            pause_reason=state.pause_reason,
            failure_kind=state.failure_kind,
            failure_message=state.failure_message,
            review_status=state.review_status,
            publication_ref=state.publication_ref,
            cleanup_status=state.cleanup_status,
            created_at=state.created_at,
            updated_at=command.occurred_at,
            completed_at=state.completed_at,
            cancelled_at=state.cancelled_at,
        )

        return AdvanceToDraftObservationSchedulingPhaseResult(
            state=next_state,
            checkpoint=checkpoint,
            planned_count=scheduling_result.planned_count,
            created_count=scheduling_result.created_count,
            already_exists_count=scheduling_result.already_exists_count,
            conflict_count=scheduling_result.conflict_count,
        )


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
