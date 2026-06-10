from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.document_segmentation.domain import (
    DocumentSegment,
    DocumentSegmentationBudget,
    DocumentSegmentKind,
    MarkdownSegmentationCommand,
    MarkdownSegmentationPolicy,
    SegmentationModelBudgetProfile,
    SegmentationPromptProfile,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
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
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)


class CreateSourceUnitsForIngestionSourceManagementPort(Protocol):
    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None: ...

    async def save_source_units(
        self,
        units: tuple[SourceUnit, ...],
    ) -> None: ...


class CreateSourceUnitsForIngestionSagaStatePort(Protocol):
    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None: ...

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None: ...


class CreateSourceUnitsForIngestionUnitOfWorkPort(Protocol):
    source_management: CreateSourceUnitsForIngestionSourceManagementPort
    saga_state: CreateSourceUnitsForIngestionSagaStatePort

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CreateSourceUnitsForIngestionCommand:
    workflow_run_id: str
    project_id: str
    source_document_ref: str
    raw_text: str
    occurred_at: datetime
    segmentation_budget: DocumentSegmentationBudget | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        _require_non_empty_text(self.raw_text, field_name="raw_text")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        if self.segmentation_budget is not None and not isinstance(
            self.segmentation_budget,
            DocumentSegmentationBudget,
        ):
            raise TypeError("segmentation_budget must be DocumentSegmentationBudget")


@dataclass(frozen=True, slots=True)
class CreateSourceUnitsForIngestionResult:
    workflow_run_id: str
    source_document_ref: str
    source_unit_count: int
    source_units_checkpoint_status: KnowledgeExtractionPhaseStatus

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        if not isinstance(self.source_unit_count, int):
            raise TypeError("source_unit_count must be int")
        if self.source_unit_count <= 0:
            raise ValueError("source_unit_count must be > 0")
        if not isinstance(
            self.source_units_checkpoint_status,
            KnowledgeExtractionPhaseStatus,
        ):
            raise TypeError(
                "source_units_checkpoint_status must be KnowledgeExtractionPhaseStatus",
            )


class CreateSourceUnitsForIngestion:
    def __init__(
        self,
        *,
        unit_of_work: CreateSourceUnitsForIngestionUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        command: CreateSourceUnitsForIngestionCommand,
    ) -> CreateSourceUnitsForIngestionResult:
        document_ref = SourceDocumentRef(command.source_document_ref)
        effective_budget = (
            command.segmentation_budget
            or default_source_ingestion_segmentation_budget()
        )

        try:
            document = await self._unit_of_work.source_management.load_source_document(
                document_ref,
            )
            if document is None:
                raise ValueError("source document not found")
            if document.project_id != command.project_id:
                raise ValueError("source document project mismatch")

            units = build_source_units_from_text(
                document=document,
                raw_text=command.raw_text,
                occurred_at=command.occurred_at,
                segmentation_budget=effective_budget,
            )

            checkpoint = _build_source_units_created_checkpoint(
                workflow_run_id=command.workflow_run_id,
                source_document_ref=command.source_document_ref,
                units=units,
                segmentation_budget=effective_budget,
                occurred_at=command.occurred_at,
            )
            state = KnowledgeExtractionWorkflowState(
                workflow_run_id=command.workflow_run_id,
                project_id=command.project_id,
                source_document_ref=command.source_document_ref,
                status=KnowledgeExtractionWorkflowStatus.RUNNING,
                current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
                checkpoints=(checkpoint,),
                created_at=command.occurred_at,
                updated_at=command.occurred_at,
            )

            await self._unit_of_work.source_management.save_source_units(units)
            await self._unit_of_work.saga_state.save_phase_checkpoint(checkpoint)
            await self._unit_of_work.saga_state.save_workflow_state(state)
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise

        return CreateSourceUnitsForIngestionResult(
            workflow_run_id=command.workflow_run_id,
            source_document_ref=command.source_document_ref,
            source_unit_count=len(units),
            source_units_checkpoint_status=checkpoint.phase_status,
        )


def default_source_ingestion_segmentation_budget() -> DocumentSegmentationBudget:
    # Production config will later pass real prompt/model request-budget values.
    return DocumentSegmentationBudget(
        prompt=SegmentationPromptProfile(
            prompt_name="draft_observation_extraction",
            prompt_token_count=2_000,
        ),
        model=SegmentationModelBudgetProfile(
            profile_name="primary_model",
            max_request_input_tokens=6_000,
            reserved_output_tokens=1_000,
        ),
    )


def build_source_units_from_text(
    *,
    document: SourceDocument,
    raw_text: str,
    occurred_at: datetime,
    segmentation_budget: DocumentSegmentationBudget | None = None,
) -> tuple[SourceUnit, ...]:
    _require_non_empty_text(raw_text, field_name="raw_text")
    _require_timezone_aware(occurred_at, field_name="occurred_at")

    effective_budget = (
        segmentation_budget or default_source_ingestion_segmentation_budget()
    )
    segments = _segment_document_text(
        document=document,
        raw_text=raw_text,
        segmentation_budget=effective_budget,
    )

    return build_source_units_from_segments(
        document=document,
        segments=segments,
        occurred_at=occurred_at,
    )


def build_source_units_from_segments(
    *,
    document: SourceDocument,
    segments: tuple[DocumentSegment, ...],
    occurred_at: datetime,
) -> tuple[SourceUnit, ...]:
    if not segments:
        raise ValueError("segments must be non-empty")
    _require_timezone_aware(occurred_at, field_name="occurred_at")

    return tuple(
        _build_source_unit_from_segment(
            document=document,
            segment=segment,
            occurred_at=occurred_at,
        )
        for segment in segments
    )


def _segment_document_text(
    *,
    document: SourceDocument,
    raw_text: str,
    segmentation_budget: DocumentSegmentationBudget,
) -> tuple[DocumentSegment, ...]:
    if document.source_format is SourceFormat.MARKDOWN:
        return MarkdownSegmentationPolicy().segment(
            MarkdownSegmentationCommand(
                document_key=document.document_ref.value,
                markdown_text=raw_text,
                budget=segmentation_budget,
            ),
        )

    return _fallback_non_markdown_segments(
        document_key=document.document_ref.value,
        raw_text=raw_text,
    )


def _fallback_non_markdown_segments(
    *,
    document_key: str,
    raw_text: str,
) -> tuple[DocumentSegment, ...]:
    paragraphs = _split_paragraphs(raw_text)
    if not paragraphs:
        raise ValueError("raw_text must contain at least one paragraph")

    return tuple(
        _build_fallback_document_segment(
            document_key=document_key,
            text=paragraph,
            ordinal=ordinal,
        )
        for ordinal, paragraph in enumerate(paragraphs)
    )


def _build_fallback_document_segment(
    *,
    document_key: str,
    text: str,
    ordinal: int,
) -> DocumentSegment:
    text_hash = sha256(text.encode("utf-8")).hexdigest()
    return DocumentSegment(
        segment_key=(
            f"segment:{document_key}:{ordinal}:"
            f"{DocumentSegmentKind.PARAGRAPH_GROUP.value}:{text_hash}"
        ),
        kind=DocumentSegmentKind.PARAGRAPH_GROUP,
        text=text,
        heading_path=(),
        ordinal=ordinal,
        estimated_tokens=max(1, (len(text) + 3) // 4),
    )


def _split_paragraphs(raw_text: str) -> tuple[str, ...]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    current_lines: list[str] = []

    for line in normalized.split("\n"):
        if line.strip():
            current_lines.append(line.rstrip())
            continue

        if current_lines:
            paragraphs.append("\n".join(current_lines).strip())
            current_lines = []

    if current_lines:
        paragraphs.append("\n".join(current_lines).strip())

    return tuple(paragraph for paragraph in paragraphs if paragraph)


def _build_source_unit_from_segment(
    *,
    document: SourceDocument,
    segment: DocumentSegment,
    occurred_at: datetime,
) -> SourceUnit:
    segment_hash = sha256(segment.segment_key.encode("utf-8")).hexdigest()
    unit_ref = SourceUnitRef(
        value=(
            f"source-unit:{document.document_ref.value}:"
            f"{segment.ordinal}:{segment_hash}"
        ),
    )

    return SourceUnit(
        unit_ref=unit_ref,
        document_ref=document.document_ref,
        unit_kind=_source_unit_kind_from_segment_kind(segment.kind),
        text=SourceUnitText(segment.text),
        heading_path=HeadingPath(segment.heading_path),
        lineage=SourceUnitLineage(()),
        ordinal=segment.ordinal,
        created_at=occurred_at,
    )


def _source_unit_kind_from_segment_kind(kind: DocumentSegmentKind) -> SourceUnitKind:
    if kind is DocumentSegmentKind.DOCUMENT_PREAMBLE:
        return SourceUnitKind.PARAGRAPH_GROUP
    if kind is DocumentSegmentKind.SECTION:
        return SourceUnitKind.SECTION
    if kind is DocumentSegmentKind.SUBSECTION:
        return SourceUnitKind.SUBSECTION
    if kind is DocumentSegmentKind.SPLIT_FRAGMENT:
        return SourceUnitKind.SPLIT_FRAGMENT
    if kind is DocumentSegmentKind.PARAGRAPH_GROUP:
        return SourceUnitKind.PARAGRAPH_GROUP
    raise ValueError(f"Unsupported document segment kind: {kind}")


def _build_source_units_created_checkpoint(
    *,
    workflow_run_id: str,
    source_document_ref: str,
    units: tuple[SourceUnit, ...],
    segmentation_budget: DocumentSegmentationBudget,
    occurred_at: datetime,
) -> KnowledgeExtractionPhaseCheckpoint:
    return KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=workflow_run_id,
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        expected_count=len(units),
        completed_count=len(units),
        failed_count=0,
        blocked_count=0,
        idempotency_key=f"source-units-created:{source_document_ref}",
        checkpoint_payload={
            "source_document_ref": source_document_ref,
            "splitter": "document_segmentation_v1",
            "segmentation_profile": segmentation_budget.model.profile_name,
            "prompt_name": segmentation_budget.prompt.prompt_name,
            "max_source_segment_tokens": segmentation_budget.max_source_segment_tokens,
            "source_unit_count": len(units),
            "source_unit_refs": [unit.unit_ref.value for unit in units],
        },
        updated_at=occurred_at,
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
