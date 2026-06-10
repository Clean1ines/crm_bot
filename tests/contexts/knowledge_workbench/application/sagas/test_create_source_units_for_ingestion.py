from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.create_source_units_for_ingestion import (
    CreateSourceUnitsForIngestion,
    CreateSourceUnitsForIngestionCommand,
    CreateSourceUnitsForIngestionResult,
    CreateSourceUnitsForIngestionSagaStatePort,
    CreateSourceUnitsForIngestionSourceManagementPort,
    build_source_units_from_text,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
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
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)


class FakeSourceManagement:
    def __init__(
        self,
        *,
        document: SourceDocument | None,
        fail_on_save_units: bool = False,
    ) -> None:
        self.document = document
        self.fail_on_save_units = fail_on_save_units
        self.saved_units: list[SourceUnit] = []
        self.loaded_refs: list[SourceDocumentRef] = []

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        self.loaded_refs.append(document_ref)
        return self.document

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        if self.fail_on_save_units:
            raise RuntimeError("source units save failed")
        self.saved_units.extend(units)


class FakeSagaState:
    def __init__(self, *, fail_on_checkpoint: bool = False) -> None:
        self.fail_on_checkpoint = fail_on_checkpoint
        self.saved_checkpoints: list[KnowledgeExtractionPhaseCheckpoint] = []
        self.saved_states: list[KnowledgeExtractionWorkflowState] = []

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None:
        if self.fail_on_checkpoint:
            raise RuntimeError("checkpoint save failed")
        self.saved_checkpoints.append(checkpoint)

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        self.saved_states.append(state)


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        source_management: FakeSourceManagement | None = None,
        saga_state: FakeSagaState | None = None,
    ) -> None:
        self.source_management_repository = source_management or FakeSourceManagement(
            document=_source_document(),
        )
        self.saga_state_repository = saga_state or FakeSagaState()
        self.source_management: CreateSourceUnitsForIngestionSourceManagementPort = (
            self.source_management_repository
        )
        self.saga_state: CreateSourceUnitsForIngestionSagaStatePort = (
            self.saga_state_repository
        )
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _source_document(*, project_id: str = "project-1") -> SourceDocument:
    return SourceDocument(
        document_ref=SourceDocumentRef("source-document:project-1:abc"),
        project_id=project_id,
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        original_filename="knowledge.md",
        created_at=_now(),
    )


def _raw_text() -> str:
    return "First paragraph.\n\nSecond paragraph.\nStill second.\n\nThird paragraph.\n"


def _command(
    *,
    project_id: str = "project-1",
    raw_text: str | None = None,
    occurred_at: datetime | None = None,
) -> CreateSourceUnitsForIngestionCommand:
    return CreateSourceUnitsForIngestionCommand(
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        project_id=project_id,
        source_document_ref="source-document:project-1:abc",
        raw_text=raw_text if raw_text is not None else _raw_text(),
        occurred_at=occurred_at or _now(),
    )


def _use_case(unit_of_work: FakeUnitOfWork) -> CreateSourceUnitsForIngestion:
    return CreateSourceUnitsForIngestion(unit_of_work=unit_of_work)


@pytest.mark.asyncio
async def test_builds_and_persists_paragraph_source_units() -> None:
    unit_of_work = FakeUnitOfWork()
    command = _command()

    result = await _use_case(unit_of_work).execute(command)

    saved_units = unit_of_work.source_management_repository.saved_units
    assert len(saved_units) == 3
    assert tuple(unit.ordinal for unit in saved_units) == (0, 1, 2)
    assert all(unit.unit_kind is SourceUnitKind.PARAGRAPH_GROUP for unit in saved_units)
    assert tuple(unit.text.value for unit in saved_units) == (
        "First paragraph.",
        "Second paragraph.\nStill second.",
        "Third paragraph.",
    )
    assert all(
        unit.document_ref.value == command.source_document_ref for unit in saved_units
    )
    assert all(unit.created_at == command.occurred_at for unit in saved_units)
    assert all(unit.unit_ref.value for unit in saved_units)
    assert result.source_unit_count == 3
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0


def test_source_unit_refs_are_deterministic() -> None:
    document = _source_document()

    units_one = build_source_units_from_text(
        document=document,
        raw_text=_raw_text(),
        occurred_at=_now(),
    )
    units_two = build_source_units_from_text(
        document=document,
        raw_text=_raw_text(),
        occurred_at=_now(),
    )
    units_three = build_source_units_from_text(
        document=document,
        raw_text="First paragraph changed.\n\nSecond paragraph.\nStill second.",
        occurred_at=_now(),
    )

    assert tuple(unit.unit_ref.value for unit in units_one) == tuple(
        unit.unit_ref.value for unit in units_two
    )
    assert tuple(unit.unit_ref.value for unit in units_one) != tuple(
        unit.unit_ref.value for unit in units_three
    )


@pytest.mark.asyncio
async def test_source_document_missing_fails_with_rollback() -> None:
    unit_of_work = FakeUnitOfWork(
        source_management=FakeSourceManagement(document=None),
    )

    with pytest.raises(ValueError, match="source document not found"):
        await _use_case(unit_of_work).execute(_command())

    assert unit_of_work.rollback_count == 1
    assert unit_of_work.commit_count == 0


@pytest.mark.asyncio
async def test_project_mismatch_fails_with_rollback() -> None:
    unit_of_work = FakeUnitOfWork(
        source_management=FakeSourceManagement(
            document=_source_document(project_id="other-project"),
        ),
    )

    with pytest.raises(ValueError, match="source document project mismatch"):
        await _use_case(unit_of_work).execute(_command(project_id="project-1"))

    assert unit_of_work.rollback_count == 1
    assert unit_of_work.commit_count == 0


def test_empty_text_fails_before_persistence_boundary() -> None:
    unit_of_work = FakeUnitOfWork()

    with pytest.raises(ValueError, match="raw_text must be non-empty"):
        _command(raw_text="   \n\t")

    assert unit_of_work.source_management_repository.saved_units == []
    assert unit_of_work.saga_state_repository.saved_checkpoints == []
    assert unit_of_work.saga_state_repository.saved_states == []
    assert unit_of_work.rollback_count == 0
    assert unit_of_work.commit_count == 0


@pytest.mark.asyncio
async def test_checkpoint_payload_and_state() -> None:
    unit_of_work = FakeUnitOfWork()
    command = _command()

    result = await _use_case(unit_of_work).execute(command)

    assert len(unit_of_work.saga_state_repository.saved_checkpoints) == 1
    checkpoint = unit_of_work.saga_state_repository.saved_checkpoints[0]
    assert checkpoint.phase_key is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert checkpoint.phase_status is KnowledgeExtractionPhaseStatus.COMPLETED
    assert checkpoint.expected_count == 3
    assert checkpoint.completed_count == 3
    assert checkpoint.checkpoint_payload["source_unit_count"] == 3
    assert len(cast(list[str], checkpoint.checkpoint_payload["source_unit_refs"])) == 3

    assert len(unit_of_work.saga_state_repository.saved_states) == 1
    state = unit_of_work.saga_state_repository.saved_states[0]
    assert state.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert state.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert state.source_document_ref == command.source_document_ref
    assert state.project_id == command.project_id

    assert (
        result.source_units_checkpoint_status
        is KnowledgeExtractionPhaseStatus.COMPLETED
    )


@pytest.mark.asyncio
async def test_rollback_on_save_source_units_failure() -> None:
    unit_of_work = FakeUnitOfWork(
        source_management=FakeSourceManagement(
            document=_source_document(),
            fail_on_save_units=True,
        ),
    )

    with pytest.raises(RuntimeError, match="source units save failed"):
        await _use_case(unit_of_work).execute(_command())

    assert unit_of_work.rollback_count == 1
    assert unit_of_work.commit_count == 0
    assert unit_of_work.saga_state_repository.saved_checkpoints == []
    assert unit_of_work.saga_state_repository.saved_states == []


@pytest.mark.asyncio
async def test_rollback_on_checkpoint_failure() -> None:
    unit_of_work = FakeUnitOfWork(
        saga_state=FakeSagaState(fail_on_checkpoint=True),
    )

    with pytest.raises(RuntimeError, match="checkpoint save failed"):
        await _use_case(unit_of_work).execute(_command())

    assert unit_of_work.rollback_count == 1
    assert unit_of_work.commit_count == 0


@pytest.mark.asyncio
async def test_no_future_phases() -> None:
    unit_of_work = FakeUnitOfWork()

    await _use_case(unit_of_work).execute(_command())

    saved_phase_keys = {
        checkpoint.phase_key
        for checkpoint in unit_of_work.saga_state_repository.saved_checkpoints
    }
    assert KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED not in saved_phase_keys
    assert KnowledgeExtractionPhaseKey.PROMPT_A_WORK_COMPLETED not in saved_phase_keys
    assert (
        KnowledgeExtractionPhaseKey.PROMPT_A_ARTIFACTS_APPLIED not in saved_phase_keys
    )


def test_command_and_result_validation() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        CreateSourceUnitsForIngestionCommand(
            workflow_run_id=" ",
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            raw_text="Text",
            occurred_at=_now(),
        )

    with pytest.raises(ValueError, match="raw_text must be non-empty"):
        CreateSourceUnitsForIngestionCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            raw_text=" ",
            occurred_at=_now(),
        )

    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        CreateSourceUnitsForIngestionCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            raw_text="Text",
            occurred_at=datetime(2026, 6, 10, 12, 0),
        )

    with pytest.raises(ValueError, match="source_unit_count must be > 0"):
        CreateSourceUnitsForIngestionResult(
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            source_unit_count=0,
            source_units_checkpoint_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        )

    with pytest.raises(
        TypeError,
        match="source_units_checkpoint_status must be KnowledgeExtractionPhaseStatus",
    ):
        CreateSourceUnitsForIngestionResult(
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            source_unit_count=1,
            source_units_checkpoint_status=cast(
                KnowledgeExtractionPhaseStatus,
                "COMPLETED",
            ),
        )


def test_create_source_units_for_ingestion_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "create_source_units_for_ingestion.py",
    ).read_text(encoding="utf-8")

    required_markers = [
        "CreateSourceUnitsForIngestion",
        "CreateSourceUnitsForIngestionCommand",
        "CreateSourceUnitsForIngestionResult",
        "CreateSourceUnitsForIngestionUnitOfWorkPort",
        "build_source_units_from_text",
        "SourceUnit",
        "SourceUnitRef",
        "SourceUnitKind.PARAGRAPH_GROUP",
        "SourceUnitText",
        "HeadingPath",
        "SourceUnitLineage",
        "SOURCE_UNITS_CREATED",
        "save_source_units",
        "save_phase_checkpoint",
        "save_workflow_state",
        "commit",
        "rollback",
    ]
    forbidden_markers = [
        "fastapi",
        "HTTPException",
        "Depends",
        "Header",
        "Request",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "Postgres",
        "UserRepository",
        "ProjectRepository",
        "get_current_user_id",
        "SourceParserPort",
        "RunClaimExtractionStageAsync",
        "DraftObservationExtractionSchedulingReconciler",
        "PROMPT_A_WORK_SCHEDULED",
        "PROMPT_A_WORK_COMPLETED",
        "PROMPT_A_ARTIFACTS_APPLIED",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "queue",
        "Queue",
        "pdf",
        "Pdf",
        "openpyxl",
        "pandas",
        "markdown",
        "BeautifulSoup",
        "emit_command",
        "record_command",
        "event_was_processed",
        "record_processed_event",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
