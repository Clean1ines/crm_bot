from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    KnowledgeExtractionSourcePhaseReconciler,
    SourcePhaseReconciliationResult,
    SourcePhaseReconciliationStatus,
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

ROOT = Path(__file__).resolve().parents[5]
RECONCILER = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "application"
    / "sagas"
    / "knowledge_extraction_source_phase_reconciliation.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _state() -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        "workflow-1",
        "project-1",
        "source-document-1",
        KnowledgeExtractionWorkflowStatus.RUNNING,
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
    )


def _document() -> SourceDocument:
    return SourceDocument(
        SourceDocumentRef("source-document-1"),
        "project-1",
        SourceFormat.MARKDOWN,
        "sha256:abc",
        _now(),
        "knowledge.md",
    )


def _unit(unit_ref: str, ordinal: int) -> SourceUnit:
    return SourceUnit(
        SourceUnitRef(unit_ref),
        SourceDocumentRef("source-document-1"),
        SourceUnitKind.SECTION,
        SourceUnitText("section text"),
        HeadingPath(("Section",)),
        SourceUnitLineage(),
        ordinal,
        _now(),
    )


class FakeSourceRepository(SourceManagementRepositoryPort):
    def __init__(
        self, document: SourceDocument | None, units: tuple[SourceUnit, ...] = ()
    ) -> None:
        self._document = document
        self._units = units
        self.loaded_document_refs: list[SourceDocumentRef] = []
        self.listed_document_refs: list[SourceDocumentRef] = []
        self.saved_documents: list[SourceDocument] = []
        self.saved_units: list[tuple[SourceUnit, ...]] = []

    async def save_source_document(self, document: SourceDocument) -> None:
        self.saved_documents.append(document)

    async def load_source_document(
        self, document_ref: SourceDocumentRef
    ) -> SourceDocument | None:
        self.loaded_document_refs.append(document_ref)
        return self._document

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        self.saved_units.append(units)

    async def list_source_units_for_document(
        self, document_ref: SourceDocumentRef
    ) -> tuple[SourceUnit, ...]:
        self.listed_document_refs.append(document_ref)
        return self._units

    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        for unit in self._units:
            if unit.unit_ref == unit_ref:
                return unit
        return None


@pytest.mark.asyncio
async def test_missing_source_document_returns_missing_without_listing_units() -> None:
    repository = FakeSourceRepository(None)
    result = await KnowledgeExtractionSourcePhaseReconciler(
        source_repository=repository
    ).reconcile_source_phases(_state())

    assert result.source_document_present is False
    assert result.source_unit_count == 0
    assert (
        result.document_phase_status
        is SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_MISSING
    )
    assert (
        result.source_units_phase_status
        is SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING
    )
    assert repository.loaded_document_refs == [SourceDocumentRef("source-document-1")]
    assert repository.listed_document_refs == []


@pytest.mark.asyncio
async def test_source_document_present_but_no_units() -> None:
    result = await KnowledgeExtractionSourcePhaseReconciler(
        source_repository=FakeSourceRepository(_document())
    ).reconcile_source_phases(_state())

    assert result.source_document_present is True
    assert result.source_unit_count == 0
    assert (
        result.document_phase_status
        is SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT
    )
    assert (
        result.source_units_phase_status
        is SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING
    )


@pytest.mark.asyncio
async def test_source_document_and_units_present() -> None:
    repository = FakeSourceRepository(
        _document(),
        (_unit("source-document-1.unit.0", 0), _unit("source-document-1.unit.1", 1)),
    )
    result = await KnowledgeExtractionSourcePhaseReconciler(
        source_repository=repository
    ).reconcile_source_phases(_state())

    assert result.source_document_present is True
    assert result.source_unit_count == 2
    assert (
        result.document_phase_status
        is SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT
    )
    assert (
        result.source_units_phase_status
        is SourcePhaseReconciliationStatus.SOURCE_UNITS_PRESENT
    )


def test_result_validates_inconsistent_shape() -> None:
    with pytest.raises(ValueError):
        SourcePhaseReconciliationResult(
            "workflow-1",
            "source-document-1",
            False,
            1,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_MISSING,
            SourcePhaseReconciliationStatus.SOURCE_UNITS_PRESENT,
        )
    with pytest.raises(ValueError):
        SourcePhaseReconciliationResult(
            "workflow-1",
            "source-document-1",
            True,
            0,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_MISSING,
            SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
        )
    with pytest.raises(ValueError):
        SourcePhaseReconciliationResult(
            "workflow-1",
            "source-document-1",
            True,
            0,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
            SourcePhaseReconciliationStatus.SOURCE_UNITS_PRESENT,
        )
    with pytest.raises(ValueError):
        SourcePhaseReconciliationResult(
            "workflow-1",
            "source-document-1",
            True,
            -1,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
            SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
        )
    with pytest.raises(ValueError):
        SourcePhaseReconciliationResult(
            " ",
            "source-document-1",
            True,
            0,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
            SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
        )
    with pytest.raises(ValueError):
        SourcePhaseReconciliationResult(
            "workflow-1",
            " ",
            True,
            0,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
            SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
        )


def test_suggested_checkpoint_statuses() -> None:
    missing_document = SourcePhaseReconciliationResult(
        "workflow-1",
        "source-document-1",
        False,
        0,
        SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_MISSING,
        SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
    )
    present_without_units = SourcePhaseReconciliationResult(
        "workflow-1",
        "source-document-1",
        True,
        0,
        SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
        SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
    )
    present_with_units = SourcePhaseReconciliationResult(
        "workflow-1",
        "source-document-1",
        True,
        1,
        SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
        SourcePhaseReconciliationStatus.SOURCE_UNITS_PRESENT,
    )

    assert (
        missing_document.suggested_checkpoint_status_for_document()
        is KnowledgeExtractionPhaseStatus.BLOCKED
    )
    assert (
        present_without_units.suggested_checkpoint_status_for_document()
        is KnowledgeExtractionPhaseStatus.COMPLETED
    )
    assert (
        present_without_units.suggested_checkpoint_status_for_source_units()
        is KnowledgeExtractionPhaseStatus.NOT_STARTED
    )
    assert (
        present_with_units.suggested_checkpoint_status_for_source_units()
        is KnowledgeExtractionPhaseStatus.COMPLETED
    )


def test_source_guard() -> None:
    text = RECONCILER.read_text(encoding="utf-8")
    required_markers = (
        "KnowledgeExtractionSourcePhaseReconciler",
        "SourcePhaseReconciliationResult",
        "SourcePhaseReconciliationStatus",
        "SourceManagementRepositoryPort",
        "load_source_document",
        "list_source_units_for_document",
        "SOURCE_DOCUMENT_MISSING",
        "SOURCE_DOCUMENT_PRESENT",
        "SOURCE_UNITS_MISSING",
        "SOURCE_UNITS_PRESENT",
    )
    forbidden_markers = (
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
        "PostgresSourceManagementRepository",
        "PostgresKnowledgeExtractionSagaStateRepository",
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "ApplyDraftClaimObservationArtifactAsync",
        "knowledge_workbench_documents",
        "knowledge_workbench_document_sections",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_" + "workbench_document",
        "emit_command",
        "record_command",
        "save_phase_checkpoint",
        "save_workflow_state",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
