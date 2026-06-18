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
from src.contexts.knowledge_workbench.document_segmentation.domain import (
    DocumentSegmentationBudget,
    SegmentationModelBudgetProfile,
    SegmentationPromptProfile,
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


def _source_document(
    *,
    project_id: str = "project-1",
    source_format: SourceFormat = SourceFormat.MARKDOWN,
) -> SourceDocument:
    return SourceDocument(
        document_ref=SourceDocumentRef("source-document:project-1:abc"),
        project_id=project_id,
        source_format=source_format,
        content_hash="sha256:abc",
        original_filename="knowledge.md",
        created_at=_now(),
    )


def _markdown_h1_text() -> str:
    return """# Alpha

A1.

# Beta

B1.
"""


def _plain_text() -> str:
    return "First paragraph.\n\nSecond paragraph.\nStill second.\n\nThird paragraph.\n"


def _budget(
    *,
    prompt_name: str = "test_prompt",
    profile_name: str = "primary_model",
    max_request_input_tokens: int = 100,
    reserved_output_tokens: int = 0,
) -> DocumentSegmentationBudget:
    return DocumentSegmentationBudget(
        prompt=SegmentationPromptProfile(
            prompt_name=prompt_name,
            prompt_token_count=0,
        ),
        model=SegmentationModelBudgetProfile(
            profile_name=profile_name,
            max_request_input_tokens=max_request_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
        ),
    )


def _command(
    *,
    project_id: str = "project-1",
    raw_text: str | None = None,
    occurred_at: datetime | None = None,
    segmentation_budget: DocumentSegmentationBudget | None = None,
) -> CreateSourceUnitsForIngestionCommand:
    return CreateSourceUnitsForIngestionCommand(
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        project_id=project_id,
        source_document_ref="source-document:project-1:abc",
        raw_text=raw_text if raw_text is not None else _markdown_h1_text(),
        occurred_at=occurred_at or _now(),
        segmentation_budget=segmentation_budget,
    )


def _use_case(unit_of_work: FakeUnitOfWork) -> CreateSourceUnitsForIngestion:
    return CreateSourceUnitsForIngestion(unit_of_work=unit_of_work)


@pytest.mark.asyncio
async def test_markdown_h1_source_units_are_section_units() -> None:
    unit_of_work = FakeUnitOfWork()
    command = _command(
        raw_text=_markdown_h1_text(),
        segmentation_budget=_budget(max_request_input_tokens=100),
    )

    result = await _use_case(unit_of_work).execute(command)

    saved_units = unit_of_work.source_management_repository.saved_units
    assert len(saved_units) == 2
    assert tuple(unit.ordinal for unit in saved_units) == (0, 1)
    assert tuple(unit.unit_kind for unit in saved_units) == (
        SourceUnitKind.SECTION,
        SourceUnitKind.SECTION,
    )
    assert tuple(unit.heading_path.parts for unit in saved_units) == (
        ("Alpha",),
        ("Beta",),
    )
    assert saved_units[0].text.value.startswith("# Alpha")
    assert saved_units[1].text.value.startswith("# Beta")
    assert result.source_unit_count == 2
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0


@pytest.mark.asyncio
async def test_oversized_markdown_h1_uses_balanced_document_segmentation() -> None:
    paragraphs = "\n\n".join(f"p{index} aa bb" for index in range(1, 11))
    raw_text = f"# Alpha\n\n{paragraphs}"
    unit_of_work = FakeUnitOfWork()
    command = _command(
        raw_text=raw_text,
        segmentation_budget=_budget(max_request_input_tokens=18),
    )

    await _use_case(unit_of_work).execute(command)

    saved_units = unit_of_work.source_management_repository.saved_units
    assert len(saved_units) == 2
    assert len(saved_units) != 10
    assert all(unit.unit_kind is SourceUnitKind.SPLIT_FRAGMENT for unit in saved_units)
    assert all(unit.heading_path.parts == ("Alpha",) for unit in saved_units)


def test_source_unit_refs_are_deterministic_from_segment_keys() -> None:
    document = _source_document()
    budget = _budget(max_request_input_tokens=100)

    units_one = build_source_units_from_text(
        document=document,
        raw_text=_markdown_h1_text(),
        occurred_at=_now(),
        segmentation_budget=budget,
    )
    units_two = build_source_units_from_text(
        document=document,
        raw_text=_markdown_h1_text(),
        occurred_at=_now(),
        segmentation_budget=budget,
    )
    units_three = build_source_units_from_text(
        document=document,
        raw_text="# Alpha\n\nChanged.",
        occurred_at=_now(),
        segmentation_budget=budget,
    )

    assert tuple(unit.unit_ref.value for unit in units_one) == tuple(
        unit.unit_ref.value for unit in units_two
    )
    assert tuple(unit.unit_ref.value for unit in units_one) != tuple(
        unit.unit_ref.value for unit in units_three
    )


def test_non_markdown_fallback_packs_adjacent_paragraphs_when_budget_allows() -> None:
    document = _source_document(source_format=SourceFormat.PLAIN_TEXT)

    units = build_source_units_from_text(
        document=document,
        raw_text=_plain_text(),
        occurred_at=_now(),
        segmentation_budget=_budget(max_request_input_tokens=100),
    )

    assert len(units) == 1
    assert all(unit.unit_kind is SourceUnitKind.PARAGRAPH_GROUP for unit in units)
    assert tuple(unit.heading_path.parts for unit in units) == ((),)
    assert units[0].text.value == (
        "First paragraph.\n\nSecond paragraph.\nStill second.\n\nThird paragraph."
    )


@pytest.mark.asyncio
async def test_checkpoint_payload_contains_segmentation_metadata() -> None:
    unit_of_work = FakeUnitOfWork()
    command = _command(
        raw_text=_markdown_h1_text(),
        segmentation_budget=_budget(max_request_input_tokens=100),
    )

    await _use_case(unit_of_work).execute(command)

    checkpoint = unit_of_work.saga_state_repository.saved_checkpoints[0]
    payload = checkpoint.checkpoint_payload
    assert payload["splitter"] == "document_segmentation_v1"
    assert payload["segmentation_profile"] == "primary_model"
    assert payload["prompt_name"] == "test_prompt"
    assert payload["max_source_segment_tokens"] == 100
    assert payload["source_unit_count"] == 2
    assert len(cast(list[str], payload["source_unit_refs"])) == 2


@pytest.mark.asyncio
async def test_command_accepts_explicit_segmentation_budget() -> None:
    unit_of_work = FakeUnitOfWork()
    command = _command(
        raw_text=_markdown_h1_text(),
        segmentation_budget=_budget(
            prompt_name="custom_prompt",
            profile_name="custom_primary_model",
            max_request_input_tokens=50,
        ),
    )

    await _use_case(unit_of_work).execute(command)

    checkpoint = unit_of_work.saga_state_repository.saved_checkpoints[0]
    assert checkpoint.checkpoint_payload["prompt_name"] == "custom_prompt"
    assert (
        checkpoint.checkpoint_payload["segmentation_profile"] == "custom_primary_model"
    )


@pytest.mark.asyncio
async def test_markdown_h1_no_longer_uses_paragraph_only_behavior_when_it_fits() -> (
    None
):
    raw_text = """# Alpha

A1.

A2.

# Beta

B1.

B2.
"""
    unit_of_work = FakeUnitOfWork()
    command = _command(
        raw_text=raw_text,
        segmentation_budget=_budget(max_request_input_tokens=100),
    )

    await _use_case(unit_of_work).execute(command)

    saved_units = unit_of_work.source_management_repository.saved_units
    assert len(saved_units) == 2
    assert len(saved_units) != 4
    assert all(unit.unit_kind is SourceUnitKind.SECTION for unit in saved_units)


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
    command = _command(
        raw_text=_markdown_h1_text(),
        segmentation_budget=_budget(max_request_input_tokens=100),
    )

    result = await _use_case(unit_of_work).execute(command)

    assert len(unit_of_work.saga_state_repository.saved_checkpoints) == 1
    checkpoint = unit_of_work.saga_state_repository.saved_checkpoints[0]
    assert checkpoint.phase_key is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert checkpoint.phase_status is KnowledgeExtractionPhaseStatus.COMPLETED
    assert checkpoint.expected_count == 2
    assert checkpoint.completed_count == 2
    assert checkpoint.checkpoint_payload["source_unit_count"] == 2
    assert len(cast(list[str], checkpoint.checkpoint_payload["source_unit_refs"])) == 2

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
    assert (
        KnowledgeExtractionPhaseKey.CLAIM_BUILDER_WORK_SCHEDULED not in saved_phase_keys
    )
    assert (
        KnowledgeExtractionPhaseKey.CLAIM_BUILDER_SECTION_EXTRACTION_COMPLETED
        not in saved_phase_keys
    )
    assert (
        KnowledgeExtractionPhaseKey.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED
        not in saved_phase_keys
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

    with pytest.raises(TypeError, match="segmentation_budget must be"):
        CreateSourceUnitsForIngestionCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            raw_text="Text",
            occurred_at=_now(),
            segmentation_budget=cast(DocumentSegmentationBudget, object()),
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
        "MarkdownSegmentationPolicy",
        "MarkdownSegmentationCommand",
        "DocumentSegmentationBudget",
        "SegmentationPromptProfile",
        "SegmentationModelBudgetProfile",
        "DocumentSegment",
        "DocumentSegmentKind",
        "build_source_units_from_segments",
        "document_segmentation_v1",
        "max_source_segment_tokens",
        "primary_model",
        "claim_builder_section_extraction",
        "CreateSourceUnitsForIngestion",
        "CreateSourceUnitsForIngestionCommand",
        "CreateSourceUnitsForIngestionResult",
        "CreateSourceUnitsForIngestionUnitOfWorkPort",
        "build_source_units_from_text",
        "SourceUnit",
        "SourceUnitRef",
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
        "context_window_tokens",
        "max_output_tokens",
        "ModelProfile",
        "RateLimitProfile",
        "qwen",
        "Qwen",
        "Groq",
        "src.contexts.llm_runtime",
        "tiktoken",
        "transformers",
        "fastapi",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "RunClaimExtractionStageAsync",
        "CLAIM_BUILDER_WORK_SCHEDULED",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "queue",
        "worker_loop",
        "openpyxl",
        "pandas",
        "BeautifulSoup",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
