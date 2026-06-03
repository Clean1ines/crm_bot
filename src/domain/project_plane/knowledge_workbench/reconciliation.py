from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared import (
    DocumentId,
    DomainInvariantError,
    ProjectId,
    ReconciliationRunId,
    RelationId,
    SurfaceId,
    require_project_id,
)


class ProjectSurfaceReconciliationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CrossDocumentSurfaceRelationType(StrEnum):
    DUPLICATE = "duplicate"
    COMPLEMENTS = "complements"
    CONTRADICTS = "contradicts"
    PARENT_CHILD = "parent_child"
    OVERLAP = "overlap"


class CrossDocumentSurfaceRelationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ProjectSurfaceReconciliationRun:
    reconciliation_run_id: ReconciliationRunId
    project_id: ProjectId
    input_document_ids: tuple[DocumentId, ...]
    status: ProjectSurfaceReconciliationStatus

    def __post_init__(self) -> None:
        if not self.reconciliation_run_id:
            raise DomainInvariantError("reconciliation_run_id is required")
        require_project_id(self.project_id)
        if len(self.input_document_ids) < 2:
            raise DomainInvariantError(
                "project surface reconciliation requires at least two documents"
            )


@dataclass(frozen=True, slots=True)
class CrossDocumentSurfaceRelation:
    relation_id: RelationId
    project_id: ProjectId
    source_document_id: DocumentId
    target_document_id: DocumentId
    source_surface_id: SurfaceId
    target_surface_id: SurfaceId
    relation_type: CrossDocumentSurfaceRelationType
    confidence: float
    status: CrossDocumentSurfaceRelationStatus

    def __post_init__(self) -> None:
        if not self.relation_id:
            raise DomainInvariantError("relation_id is required")
        require_project_id(self.project_id)
        if self.source_document_id == self.target_document_id:
            raise DomainInvariantError(
                "cross-document relation requires different documents"
            )
        if self.source_surface_id == self.target_surface_id:
            raise DomainInvariantError(
                "cross-document relation requires different surfaces"
            )
        if self.confidence < 0 or self.confidence > 1:
            raise DomainInvariantError("confidence must be between 0 and 1")
