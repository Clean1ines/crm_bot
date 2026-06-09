from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import DraftObservationExtractionWorkIndexPort
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import KnowledgeExtractionPhaseKey, KnowledgeExtractionPhaseStatus, KnowledgeExtractionWorkflowState


class DraftObservationExtractionSchedulingStatus(StrEnum):
    SOURCE_UNITS_NOT_READY = "SOURCE_UNITS_NOT_READY"
    READY_TO_SCHEDULE = "READY_TO_SCHEDULE"
    PARTIALLY_SCHEDULED = "PARTIALLY_SCHEDULED"
    ALREADY_SCHEDULED = "ALREADY_SCHEDULED"


@dataclass(frozen=True, slots=True)
class DraftObservationExtractionSchedulingDecision:
    workflow_run_id: str
    source_document_ref: str
    expected_source_unit_count: int
    scheduled_work_item_count: int
    status: DraftObservationExtractionSchedulingStatus

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.source_document_ref, "source_document_ref")
        _require_non_negative(self.expected_source_unit_count, "expected_source_unit_count")
        _require_non_negative(self.scheduled_work_item_count, "scheduled_work_item_count")
        expected_status = _status_for_counts(
            self.expected_source_unit_count,
            self.scheduled_work_item_count,
        )
        if self.status is not expected_status:
            raise ValueError("scheduling decision status mismatch")

    def suggested_checkpoint_status(self) -> KnowledgeExtractionPhaseStatus:
        if self.status is DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY:
            return KnowledgeExtractionPhaseStatus.NOT_STARTED
        if self.status is DraftObservationExtractionSchedulingStatus.READY_TO_SCHEDULE:
            return KnowledgeExtractionPhaseStatus.READY
        if self.status is DraftObservationExtractionSchedulingStatus.PARTIALLY_SCHEDULED:
            return KnowledgeExtractionPhaseStatus.IN_PROGRESS
        return KnowledgeExtractionPhaseStatus.COMPLETED


class DraftObservationExtractionSchedulingReconciler:
    def __init__(self, *, work_index: DraftObservationExtractionWorkIndexPort) -> None:
        self._work_index = work_index

    async def reconcile_scheduling(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> DraftObservationExtractionSchedulingDecision:
        source_units_checkpoint = _source_units_checkpoint(state)
        if source_units_checkpoint is None:
            return _source_units_not_ready_decision(state)
        if source_units_checkpoint.phase_status is not KnowledgeExtractionPhaseStatus.COMPLETED:
            return _source_units_not_ready_decision(state)
        expected_count = _source_unit_count_from_payload(
            source_units_checkpoint.checkpoint_payload,
        )
        if expected_count == 0:
            return _source_units_not_ready_decision(state)
        scheduled_count = await self._work_index.count_scheduled_draft_observation_work_items(
            workflow_run_id=state.workflow_run_id,
            source_document_ref=state.source_document_ref,
        )
        return DraftObservationExtractionSchedulingDecision(
            workflow_run_id=state.workflow_run_id,
            source_document_ref=state.source_document_ref,
            expected_source_unit_count=expected_count,
            scheduled_work_item_count=scheduled_count,
            status=_status_for_counts(expected_count, scheduled_count),
        )


def _source_units_checkpoint(state: KnowledgeExtractionWorkflowState):
    for checkpoint in state.checkpoints:
        if checkpoint.phase_key is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED:
            return checkpoint
    return None


def _source_units_not_ready_decision(
    state: KnowledgeExtractionWorkflowState,
) -> DraftObservationExtractionSchedulingDecision:
    return DraftObservationExtractionSchedulingDecision(
        workflow_run_id=state.workflow_run_id,
        source_document_ref=state.source_document_ref,
        expected_source_unit_count=0,
        scheduled_work_item_count=0,
        status=DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY,
    )


def _source_unit_count_from_payload(payload) -> int:
    value = payload.get("source_unit_count")
    if not isinstance(value, int):
        raise TypeError("source_unit_count checkpoint payload must be int")
    if value < 0:
        raise ValueError("source_unit_count checkpoint payload must be >= 0")
    return value


def _status_for_counts(
    expected_source_unit_count: int,
    scheduled_work_item_count: int,
) -> DraftObservationExtractionSchedulingStatus:
    if expected_source_unit_count == 0:
        return DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY
    if scheduled_work_item_count == 0:
        return DraftObservationExtractionSchedulingStatus.READY_TO_SCHEDULE
    if scheduled_work_item_count < expected_source_unit_count:
        return DraftObservationExtractionSchedulingStatus.PARTIALLY_SCHEDULED
    return DraftObservationExtractionSchedulingStatus.ALREADY_SCHEDULED


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
