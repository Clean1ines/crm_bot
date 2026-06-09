from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    SourcePhaseReconciliationResult,
)


def source_reconciliation_checkpoints(
    state: KnowledgeExtractionWorkflowState,
    source_result: SourcePhaseReconciliationResult,
    occurred_at: datetime,
) -> tuple[KnowledgeExtractionPhaseCheckpoint, KnowledgeExtractionPhaseCheckpoint]:
    document_checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=state.workflow_run_id,
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        phase_status=source_result.suggested_checkpoint_status_for_document(),
        expected_count=1,
        completed_count=1 if source_result.source_document_present else 0,
        failed_count=0,
        blocked_count=0 if source_result.source_document_present else 1,
        idempotency_key=f"source-document:{state.source_document_ref}",
        checkpoint_payload={
            "source_document_ref": state.source_document_ref,
            "source_document_present": source_result.source_document_present,
        },
        updated_at=occurred_at,
    )
    units_checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=state.workflow_run_id,
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=source_result.suggested_checkpoint_status_for_source_units(),
        expected_count=source_result.source_unit_count,
        completed_count=source_result.source_unit_count,
        failed_count=0,
        blocked_count=0,
        idempotency_key=f"source-units:{state.source_document_ref}",
        checkpoint_payload={
            "source_document_ref": state.source_document_ref,
            "source_unit_count": source_result.source_unit_count,
        },
        updated_at=occurred_at,
    )
    return document_checkpoint, units_checkpoint


def state_with_source_reconciliation(
    state: KnowledgeExtractionWorkflowState,
    source_result: SourcePhaseReconciliationResult,
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...],
    occurred_at: datetime,
) -> KnowledgeExtractionWorkflowState:
    merged_checkpoints = replace_source_checkpoints(state.checkpoints, checkpoints)
    if not source_result.source_document_present:
        return _copy_state(
            state,
            KnowledgeExtractionWorkflowStatus.PAUSED,
            KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
            "source_document_missing",
            merged_checkpoints,
            occurred_at,
        )
    if source_result.source_unit_count == 0:
        return _copy_state(
            state,
            KnowledgeExtractionWorkflowStatus.PAUSED,
            KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
            "source_units_missing",
            merged_checkpoints,
            occurred_at,
        )
    return _copy_state(
        state,
        KnowledgeExtractionWorkflowStatus.RUNNING,
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        None,
        merged_checkpoints,
        occurred_at,
    )


def replace_source_checkpoints(
    existing: tuple[KnowledgeExtractionPhaseCheckpoint, ...],
    replacements: tuple[KnowledgeExtractionPhaseCheckpoint, ...],
) -> tuple[KnowledgeExtractionPhaseCheckpoint, ...]:
    replacement_phase_keys = {checkpoint.phase_key for checkpoint in replacements}
    kept = tuple(
        checkpoint
        for checkpoint in existing
        if checkpoint.phase_key not in replacement_phase_keys
    )
    return kept + replacements


def _copy_state(
    state: KnowledgeExtractionWorkflowState,
    status: KnowledgeExtractionWorkflowStatus,
    current_phase: KnowledgeExtractionPhaseKey,
    pause_reason: str | None,
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...],
    updated_at: datetime,
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id=state.workflow_run_id,
        project_id=state.project_id,
        source_document_ref=state.source_document_ref,
        status=status,
        current_phase=current_phase,
        checkpoints=checkpoints,
        pause_reason=pause_reason,
        failure_kind=state.failure_kind,
        failure_message=state.failure_message,
        review_status=state.review_status,
        publication_ref=state.publication_ref,
        cleanup_status=state.cleanup_status,
        created_at=state.created_at,
        updated_at=updated_at,
        completed_at=state.completed_at,
        cancelled_at=state.cancelled_at,
    )
