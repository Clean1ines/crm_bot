from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.domain.project_plane.knowledge_workbench.errors import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)


class WorkbenchDeleteDocument(Protocol):
    project_id: str
    document_id: str
    status: KnowledgeDocumentStatus
    current_processing_run_id: str | None


class WorkbenchDeleteProcessingRun(Protocol):
    project_id: str
    document_id: str
    processing_run_id: str
    status: ProcessingRunStatus


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentDeleteTransition:
    project_id: str
    document_id: str
    deleted_at: datetime
    document_status_after: KnowledgeDocumentStatus
    processing_run_id: str | None
    processing_run_status_after: ProcessingRunStatus | None
    runtime_publication_should_be_removed: bool = True
    pending_queue_jobs_should_be_removed: bool = True

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise DomainInvariantError("project_id is required")
        if not self.document_id.strip():
            raise DomainInvariantError("document_id is required")
        if self.document_status_after is not KnowledgeDocumentStatus.DELETED:
            raise DomainInvariantError("delete transition must delete document")
        if (
            self.processing_run_id is None
            and self.processing_run_status_after is not None
        ):
            raise DomainInvariantError(
                "processing run status requires processing_run_id"
            )
        if self.processing_run_id is not None and not self.processing_run_id.strip():
            raise DomainInvariantError("processing_run_id must be non-empty")


def decide_workbench_document_delete_transition(
    *,
    document: WorkbenchDeleteDocument,
    current_processing_run: WorkbenchDeleteProcessingRun | None,
    deleted_at: datetime,
) -> WorkbenchDocumentDeleteTransition:
    if document.status is KnowledgeDocumentStatus.DELETED:
        raise DomainInvariantError("document is already deleted")

    processing_run_id = str(document.current_processing_run_id or "").strip() or None

    if current_processing_run is not None:
        if current_processing_run.project_id != document.project_id:
            raise DomainInvariantError("processing run project_id mismatch")
        if current_processing_run.document_id != document.document_id:
            raise DomainInvariantError("processing run document_id mismatch")
        if processing_run_id is not None and (
            current_processing_run.processing_run_id != processing_run_id
        ):
            raise DomainInvariantError("current processing_run_id mismatch")
        processing_run_id = current_processing_run.processing_run_id

    processing_run_status_after = (
        ProcessingRunStatus.DELETED if processing_run_id is not None else None
    )

    return WorkbenchDocumentDeleteTransition(
        project_id=document.project_id,
        document_id=document.document_id,
        deleted_at=deleted_at,
        document_status_after=KnowledgeDocumentStatus.DELETED,
        processing_run_id=processing_run_id,
        processing_run_status_after=processing_run_status_after,
    )


__all__ = [
    "WorkbenchDocumentDeleteTransition",
    "decide_workbench_document_delete_transition",
]
