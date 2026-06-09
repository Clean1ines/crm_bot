from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)


class SourcePhaseReconciliationStatus(StrEnum):
    SOURCE_DOCUMENT_MISSING = "SOURCE_DOCUMENT_MISSING"
    SOURCE_DOCUMENT_PRESENT = "SOURCE_DOCUMENT_PRESENT"
    SOURCE_UNITS_MISSING = "SOURCE_UNITS_MISSING"
    SOURCE_UNITS_PRESENT = "SOURCE_UNITS_PRESENT"


@dataclass(frozen=True, slots=True)
class SourcePhaseReconciliationResult:
    workflow_run_id: str
    source_document_ref: str
    source_document_present: bool
    source_unit_count: int
    document_phase_status: SourcePhaseReconciliationStatus
    source_units_phase_status: SourcePhaseReconciliationStatus

    def __post_init__(self) -> None:
        if not self.workflow_run_id or not self.workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if not self.source_document_ref or not self.source_document_ref.strip():
            raise ValueError("source_document_ref must be non-empty")
        if self.source_unit_count < 0:
            raise ValueError("source_unit_count must be >= 0")
        if not self.source_document_present and self.source_unit_count != 0:
            raise ValueError("missing source document cannot have source units")
        if self.document_phase_status is not _document_status(
            self.source_document_present
        ):
            raise ValueError("document phase status mismatch")
        if self.source_units_phase_status is not _units_status(self.source_unit_count):
            raise ValueError("source units phase status mismatch")

    def suggested_checkpoint_status_for_document(
        self,
    ) -> KnowledgeExtractionPhaseStatus:
        if (
            self.document_phase_status
            is SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT
        ):
            return KnowledgeExtractionPhaseStatus.COMPLETED
        return KnowledgeExtractionPhaseStatus.BLOCKED

    def suggested_checkpoint_status_for_source_units(
        self,
    ) -> KnowledgeExtractionPhaseStatus:
        if (
            self.source_units_phase_status
            is SourcePhaseReconciliationStatus.SOURCE_UNITS_PRESENT
        ):
            return KnowledgeExtractionPhaseStatus.COMPLETED
        return KnowledgeExtractionPhaseStatus.NOT_STARTED


class KnowledgeExtractionSourcePhaseReconciler:
    def __init__(self, *, source_repository: SourceManagementRepositoryPort) -> None:
        self._source_repository = source_repository

    async def reconcile_source_phases(
        self, state: KnowledgeExtractionWorkflowState
    ) -> SourcePhaseReconciliationResult:
        document_ref = SourceDocumentRef(state.source_document_ref)
        document = await self._source_repository.load_source_document(document_ref)
        if document is None:
            return SourcePhaseReconciliationResult(
                state.workflow_run_id,
                state.source_document_ref,
                False,
                0,
                SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_MISSING,
                SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING,
            )
        units = await self._source_repository.list_source_units_for_document(
            document_ref
        )
        unit_count = len(units)
        return SourcePhaseReconciliationResult(
            state.workflow_run_id,
            state.source_document_ref,
            True,
            unit_count,
            SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT,
            _units_status(unit_count),
        )


def _document_status(document_present: bool) -> SourcePhaseReconciliationStatus:
    if document_present:
        return SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_PRESENT
    return SourcePhaseReconciliationStatus.SOURCE_DOCUMENT_MISSING


def _units_status(source_unit_count: int) -> SourcePhaseReconciliationStatus:
    if source_unit_count > 0:
        return SourcePhaseReconciliationStatus.SOURCE_UNITS_PRESENT
    return SourcePhaseReconciliationStatus.SOURCE_UNITS_MISSING
