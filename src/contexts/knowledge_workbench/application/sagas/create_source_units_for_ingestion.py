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
    source_units: tuple[SourceUnit, ...] = ()

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
        if not isinstance(self.source_units, tuple):
            raise TypeError("source_units must be tuple")
        if self.source_units and len(self.source_units) != self.source_unit_count:
            raise ValueError("source_units length must equal source_unit_count")
        for source_unit in self.source_units:
            if not isinstance(source_unit, SourceUnit):
                raise TypeError("source_units must contain SourceUnit")


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
            source_units=units,
        )


def default_source_ingestion_segmentation_budget() -> DocumentSegmentationBudget:
    # Keep only a small input safety gap here. Concrete output budget belongs
    # to LLM dispatch, not document segmentation.
    return DocumentSegmentationBudget(
        prompt=SegmentationPromptProfile(
            prompt_name="claim_builder_section_extraction",
            prompt_token_count=1_953,
        ),
        model=SegmentationModelBudgetProfile(
            profile_name="primary_model",
            max_request_input_tokens=6_000,
            segmentation_input_safety_gap_tokens=100,
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
    heading_first_segments = _markdown_heading_first_segments(
        document=document,
        raw_text=raw_text,
        segmentation_budget=effective_budget,
    )
    segments = (
        heading_first_segments
        if heading_first_segments
        else _segment_document_text(
            document=document,
            raw_text=raw_text,
            segmentation_budget=effective_budget,
        )
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


def _markdown_heading_first_segments(
    *,
    document: SourceDocument,
    raw_text: str,
    segmentation_budget: DocumentSegmentationBudget,
) -> tuple[DocumentSegment, ...]:
    if document.source_format is not SourceFormat.MARKDOWN:
        return ()

    sections = _split_markdown_by_atx_headings(raw_text)
    if not sections:
        return ()

    segments: list[DocumentSegment] = []
    ordinal = 0

    for heading_path, section_text in sections:
        estimated_tokens = max(1, (len(section_text) + 3) // 4)
        if estimated_tokens <= segmentation_budget.max_source_segment_tokens:
            text_hash = sha256(section_text.encode("utf-8")).hexdigest()
            segments.append(
                DocumentSegment(
                    segment_key=(
                        f"segment:{document.document_ref.value}:{ordinal}:"
                        f"{DocumentSegmentKind.SECTION.value}:{text_hash}"
                    ),
                    kind=DocumentSegmentKind.SECTION,
                    text=section_text,
                    heading_path=heading_path,
                    ordinal=ordinal,
                    estimated_tokens=estimated_tokens,
                )
            )
            ordinal += 1
            continue

        nested_segments = MarkdownSegmentationPolicy().segment(
            MarkdownSegmentationCommand(
                document_key=f"{document.document_ref.value}:{ordinal}",
                markdown_text=section_text,
                budget=segmentation_budget,
            )
        )
        for nested in nested_segments:
            segments.append(
                DocumentSegment(
                    segment_key=nested.segment_key,
                    kind=DocumentSegmentKind.SPLIT_FRAGMENT,
                    text=nested.text,
                    heading_path=heading_path,
                    ordinal=ordinal,
                    estimated_tokens=nested.estimated_tokens,
                )
            )
            ordinal += 1

    return tuple(segments)


def _split_markdown_by_atx_headings(
    raw_text: str,
) -> tuple[tuple[tuple[str, ...], str], ...]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue

        marker = stripped.split(" ", 1)[0]
        if marker and set(marker) == {"#"} and 1 <= len(marker) <= 6:
            heading_level = len(marker)
            heading_title = stripped[heading_level:].strip() or stripped
            headings.append((index, heading_level, heading_title))

    if not headings:
        return ()

    split_level = _markdown_primary_split_level(headings)
    split_headings = [
        (index, level, title)
        for index, level, title in headings
        if level == split_level
    ]
    if not split_headings:
        return ()

    sections: list[tuple[tuple[str, ...], str]] = []

    preamble = "\n".join(lines[: split_headings[0][0]]).strip()
    parent_heading_path = _heading_path_before_index(
        headings=headings,
        heading_index=split_headings[0][0],
        split_level=split_level,
    )

    for position, (heading_index, _level, heading_title) in enumerate(split_headings):
        next_index = (
            split_headings[position + 1][0]
            if position + 1 < len(split_headings)
            else len(lines)
        )

        section_lines = lines[heading_index:next_index]
        if position == 0 and preamble:
            section_lines = [preamble, "", *section_lines]

        section_text = "\n".join(section_lines).strip()
        if section_text:
            sections.append(((*parent_heading_path, heading_title), section_text))

    return tuple(sections)


def _markdown_primary_split_level(
    headings: list[tuple[int, int, str]],
) -> int:
    levels = {level for _index, level, _title in headings}

    # Most product docs use one H1 title and H2 chapters.
    # Splitting by every H3/H4 creates unusable tiny sections.
    if 2 in levels:
        return 2

    return min(levels)


def _heading_path_before_index(
    *,
    headings: list[tuple[int, int, str]],
    heading_index: int,
    split_level: int,
) -> tuple[str, ...]:
    stack: list[str] = []

    for index, level, title in headings:
        if index >= heading_index:
            break
        if level >= split_level:
            continue

        stack = stack[: level - 1]
        stack.append(title)

    return tuple(stack)


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
        segmentation_budget=segmentation_budget,
    )


def _fallback_non_markdown_segments(
    *,
    document_key: str,
    raw_text: str,
    segmentation_budget: DocumentSegmentationBudget,
) -> tuple[DocumentSegment, ...]:
    paragraphs = _split_paragraphs(raw_text)
    if not paragraphs:
        raise ValueError("raw_text must contain at least one paragraph")

    packed_paragraph_groups = _pack_adjacent_paragraphs(
        paragraphs=paragraphs,
        max_tokens=segmentation_budget.max_source_segment_tokens,
    )

    return tuple(
        _build_fallback_document_segment(
            document_key=document_key,
            text=paragraph_group,
            ordinal=ordinal,
        )
        for ordinal, paragraph_group in enumerate(packed_paragraph_groups)
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


def _pack_adjacent_paragraphs(
    *,
    paragraphs: tuple[str, ...],
    max_tokens: int,
) -> tuple[str, ...]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")

    groups: list[str] = []
    current: list[str] = []

    for paragraph in paragraphs:
        candidate = "\n\n".join((*current, paragraph)).strip()
        if current and max(1, (len(candidate) + 3) // 4) > max_tokens:
            groups.append("\n\n".join(current).strip())
            current = [paragraph]
            continue
        current.append(paragraph)

    if current:
        groups.append("\n\n".join(current).strip())

    return tuple(group for group in groups if group)


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
