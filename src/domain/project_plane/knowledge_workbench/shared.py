from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)

ProjectId = str
UserId = str
DocumentId = str
SectionId = str
ProcessingRunId = str
NodeRunId = str
ArtifactId = str
RegistryId = str
FactId = str
ClaimObservationId = str
ProposalId = str
ApplicationId = str
SnapshotId = str
SurfaceId = str
RelationId = str
CurationSessionId = str
CurationChangeId = str
PublicationId = str
RuntimeEntryId = str
RagEvalRunId = str
RagEvalCaseId = str
RagEvalResultId = str
ReconciliationRunId = str
ModelInvocationId = str
ErrorReportId = str


class DomainInvariantError(ValueError):
    pass


class SourceType(StrEnum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    TEXT = "text"
    HTML = "html"
    MANUAL_NOTE = "manual_note"
    IMPORTED_PAGE = "imported_page"


@dataclass(frozen=True, slots=True)
class TimeRange:
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def duration_ms(self) -> int | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return int((self.completed_at - self.started_at).total_seconds() * 1000)


def require_project_id(project_id: ProjectId) -> None:
    if not project_id:
        raise DomainInvariantError(
            "project_id is required for every knowledge workbench artifact"
        )


def require_document_id(document_id: DocumentId) -> None:
    if not document_id:
        raise DomainInvariantError(
            "document_id is required for document-scoped artifacts"
        )


def require_processing_run_id(processing_run_id: ProcessingRunId) -> None:
    if not processing_run_id:
        raise DomainInvariantError(
            "processing_run_id is required for processing artifacts"
        )


def require_node_run_id(node_run_id: NodeRunId) -> None:
    if not node_run_id:
        raise DomainInvariantError("node_run_id is required for node-level artifacts")
