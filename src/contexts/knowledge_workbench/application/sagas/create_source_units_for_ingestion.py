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

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        _require_non_empty_text(self.raw_text, field_name="raw_text")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")


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
            )

            checkpoint = _build_source_units_created_checkpoint(
                workflow_run_id=command.workflow_run_id,
                source_document_ref=command.source_document_ref,
                units=units,
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


def build_source_units_from_text(
    *,
    document: SourceDocument,
    raw_text: str,
    occurred_at: datetime,
) -> tuple[SourceUnit, ...]:
    _require_non_empty_text(raw_text, field_name="raw_text")
    _require_timezone_aware(occurred_at, field_name="occurred_at")

    paragraphs = _split_paragraphs(raw_text)
    if not paragraphs:
        raise ValueError("raw_text must contain at least one paragraph")

    return tuple(
        _build_source_unit(
            document=document,
            paragraph_text=paragraph_text,
            ordinal=ordinal,
            occurred_at=occurred_at,
        )
        for ordinal, paragraph_text in enumerate(paragraphs)
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


def _build_source_unit(
    *,
    document: SourceDocument,
    paragraph_text: str,
    ordinal: int,
    occurred_at: datetime,
) -> SourceUnit:
    paragraph_hash = sha256(paragraph_text.encode("utf-8")).hexdigest()
    unit_ref = SourceUnitRef(
        value=f"source-unit:{document.document_ref.value}:{ordinal}:{paragraph_hash}",
    )

    return SourceUnit(
        unit_ref=unit_ref,
        document_ref=document.document_ref,
        unit_kind=SourceUnitKind.PARAGRAPH_GROUP,
        text=SourceUnitText(paragraph_text),
        heading_path=HeadingPath(()),
        lineage=SourceUnitLineage(()),
        ordinal=ordinal,
        created_at=occurred_at,
    )


def _build_source_units_created_checkpoint(
    *,
    workflow_run_id: str,
    source_document_ref: str,
    units: tuple[SourceUnit, ...],
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
