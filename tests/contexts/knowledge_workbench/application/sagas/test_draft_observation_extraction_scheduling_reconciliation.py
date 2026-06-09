from __future__ import annotations

from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas import (
    DraftObservationExtractionWorkIndexPort,
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_draft_observation_scheduling_reconciliation import (
    DraftObservationExtractionSchedulingDecision,
    DraftObservationExtractionSchedulingReconciler,
    DraftObservationExtractionSchedulingStatus,
)

ROOT = Path(__file__).resolve().parents[5]
RECONCILER = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "application"
    / "sagas"
    / "knowledge_extraction_draft_observation_scheduling_reconciliation.py"
)


def _state(
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...] = (),
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref="source-document-1",
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        checkpoints=checkpoints,
    )


def _source_units_checkpoint(
    status: KnowledgeExtractionPhaseStatus, count: object
) -> KnowledgeExtractionPhaseCheckpoint:
    return KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="workflow-1",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=status,
        expected_count=count if isinstance(count, int) and count >= 0 else 0,
        completed_count=count if isinstance(count, int) and count >= 0 else 0,
        checkpoint_payload={"source_unit_count": count},
    )


class _WorkIndex(DraftObservationExtractionWorkIndexPort):
    def __init__(self, scheduled_count: int) -> None:
        self.scheduled_count = scheduled_count
        self.calls: list[tuple[str, str]] = []

    async def count_scheduled_draft_observation_work_items(
        self,
        *,
        workflow_run_id: str,
        source_document_ref: str,
    ) -> int:
        self.calls.append((workflow_run_id, source_document_ref))
        return self.scheduled_count


@pytest.mark.asyncio
async def test_source_units_checkpoint_missing_returns_not_ready_without_index_call() -> (
    None
):
    work_index = _WorkIndex(0)
    decision = await DraftObservationExtractionSchedulingReconciler(
        work_index=work_index
    ).reconcile_scheduling(_state())

    assert decision.expected_source_unit_count == 0
    assert decision.scheduled_work_item_count == 0
    assert (
        decision.status
        is DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY
    )
    assert (
        decision.suggested_checkpoint_status()
        is KnowledgeExtractionPhaseStatus.NOT_STARTED
    )
    assert work_index.calls == []


@pytest.mark.asyncio
async def test_source_units_checkpoint_not_completed_returns_not_ready_without_index_call() -> (
    None
):
    work_index = _WorkIndex(0)
    checkpoint = _source_units_checkpoint(KnowledgeExtractionPhaseStatus.NOT_STARTED, 2)

    decision = await DraftObservationExtractionSchedulingReconciler(
        work_index=work_index
    ).reconcile_scheduling(_state((checkpoint,)))

    assert (
        decision.status
        is DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY
    )
    assert (
        decision.suggested_checkpoint_status()
        is KnowledgeExtractionPhaseStatus.NOT_STARTED
    )
    assert work_index.calls == []


@pytest.mark.asyncio
async def test_source_units_completed_with_zero_count_returns_not_ready_without_index_call() -> (
    None
):
    work_index = _WorkIndex(0)
    checkpoint = _source_units_checkpoint(KnowledgeExtractionPhaseStatus.COMPLETED, 0)

    decision = await DraftObservationExtractionSchedulingReconciler(
        work_index=work_index
    ).reconcile_scheduling(_state((checkpoint,)))

    assert (
        decision.status
        is DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY
    )
    assert work_index.calls == []


@pytest.mark.asyncio
async def test_ready_to_schedule_when_no_work_items_exist() -> None:
    work_index = _WorkIndex(0)
    checkpoint = _source_units_checkpoint(KnowledgeExtractionPhaseStatus.COMPLETED, 2)

    decision = await DraftObservationExtractionSchedulingReconciler(
        work_index=work_index
    ).reconcile_scheduling(_state((checkpoint,)))

    assert decision.expected_source_unit_count == 2
    assert decision.scheduled_work_item_count == 0
    assert (
        decision.status is DraftObservationExtractionSchedulingStatus.READY_TO_SCHEDULE
    )
    assert (
        decision.suggested_checkpoint_status() is KnowledgeExtractionPhaseStatus.READY
    )
    assert work_index.calls == [("workflow-1", "source-document-1")]


@pytest.mark.asyncio
async def test_partially_scheduled_when_some_work_items_exist() -> None:
    checkpoint = _source_units_checkpoint(KnowledgeExtractionPhaseStatus.COMPLETED, 3)

    decision = await DraftObservationExtractionSchedulingReconciler(
        work_index=_WorkIndex(1)
    ).reconcile_scheduling(_state((checkpoint,)))

    assert (
        decision.status
        is DraftObservationExtractionSchedulingStatus.PARTIALLY_SCHEDULED
    )
    assert (
        decision.suggested_checkpoint_status()
        is KnowledgeExtractionPhaseStatus.IN_PROGRESS
    )


@pytest.mark.asyncio
async def test_already_scheduled_when_enough_or_more_work_items_exist() -> None:
    checkpoint = _source_units_checkpoint(KnowledgeExtractionPhaseStatus.COMPLETED, 2)

    exact = await DraftObservationExtractionSchedulingReconciler(
        work_index=_WorkIndex(2)
    ).reconcile_scheduling(_state((checkpoint,)))
    extra = await DraftObservationExtractionSchedulingReconciler(
        work_index=_WorkIndex(3)
    ).reconcile_scheduling(_state((checkpoint,)))

    assert exact.status is DraftObservationExtractionSchedulingStatus.ALREADY_SCHEDULED
    assert (
        exact.suggested_checkpoint_status() is KnowledgeExtractionPhaseStatus.COMPLETED
    )
    assert extra.status is DraftObservationExtractionSchedulingStatus.ALREADY_SCHEDULED


@pytest.mark.asyncio
async def test_invalid_checkpoint_payload_raises() -> None:
    missing_payload = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="workflow-1",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        checkpoint_payload={},
    )
    bad_payload = _source_units_checkpoint(
        KnowledgeExtractionPhaseStatus.COMPLETED, "2"
    )
    reconciler = DraftObservationExtractionSchedulingReconciler(
        work_index=_WorkIndex(0)
    )

    with pytest.raises(TypeError):
        await reconciler.reconcile_scheduling(_state((missing_payload,)))
    with pytest.raises(TypeError):
        await reconciler.reconcile_scheduling(_state((bad_payload,)))


def test_decision_validation_catches_inconsistent_shape() -> None:
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            "workflow-1",
            "source-document-1",
            2,
            0,
            DraftObservationExtractionSchedulingStatus.PARTIALLY_SCHEDULED,
        )
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            "workflow-1",
            "source-document-1",
            2,
            1,
            DraftObservationExtractionSchedulingStatus.READY_TO_SCHEDULE,
        )
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            "workflow-1",
            "source-document-1",
            2,
            2,
            DraftObservationExtractionSchedulingStatus.PARTIALLY_SCHEDULED,
        )


def test_decision_validation_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            " ",
            "source-document-1",
            0,
            0,
            DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY,
        )
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            "workflow-1",
            " ",
            0,
            0,
            DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY,
        )
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            "workflow-1",
            "source-document-1",
            -1,
            0,
            DraftObservationExtractionSchedulingStatus.SOURCE_UNITS_NOT_READY,
        )
    with pytest.raises(ValueError):
        DraftObservationExtractionSchedulingDecision(
            "workflow-1",
            "source-document-1",
            1,
            -1,
            DraftObservationExtractionSchedulingStatus.READY_TO_SCHEDULE,
        )


def test_source_guard() -> None:
    text = RECONCILER.read_text(encoding="utf-8")
    required_markers = (
        "DraftObservationExtractionSchedulingReconciler",
        "DraftObservationExtractionSchedulingDecision",
        "DraftObservationExtractionSchedulingStatus",
        "DraftObservationExtractionWorkIndexPort",
        "count_scheduled_draft_observation_work_items",
        "SOURCE_UNITS_CREATED",
        "READY_TO_SCHEDULE",
        "PARTIALLY_SCHEDULED",
        "ALREADY_SCHEDULED",
        "SOURCE_UNITS_NOT_READY",
    )
    forbidden_markers = (
        "PromptA",
        "Prompt_A",
        "PROMPT_A",
        "asyncpg",
        "postgres",
        "Postgres",
        "src.infrastructure",
        "JobDispatcher",
        "worker_loop",
        "outbox_events",
        "published_at",
        "Groq",
        "Qwen",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "RunClaimExtractionStageAsync",
        "ProcessClaimExtractionWorkItem",
        "RecordClaimExtractionSuccess",
        "ApplyDraftClaimObservationArtifactAsync",
        "claim_extraction_stage_work_items",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_workbench_document",
        "emit_command",
        "record_command",
        "save_phase_checkpoint",
        "save_workflow_state",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
