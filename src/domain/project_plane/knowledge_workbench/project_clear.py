from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.project_plane.knowledge_workbench.errors import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)


@dataclass(frozen=True, slots=True)
class WorkbenchProjectClearTransition:
    project_id: str
    cleared_at: datetime
    document_status_after: KnowledgeDocumentStatus = KnowledgeDocumentStatus.DELETED
    processing_run_status_after: ProcessingRunStatus = ProcessingRunStatus.DELETED
    runtime_publications_should_be_removed: bool = True
    pending_queue_jobs_should_be_removed: bool = True

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise DomainInvariantError("project_id is required")
        if self.document_status_after is not KnowledgeDocumentStatus.DELETED:
            raise DomainInvariantError("project clear must delete project documents")
        if self.processing_run_status_after is not ProcessingRunStatus.DELETED:
            raise DomainInvariantError("project clear must terminalize processing runs")


def decide_workbench_project_clear_transition(
    *,
    project_id: str,
    cleared_at: datetime,
) -> WorkbenchProjectClearTransition:
    if not project_id.strip():
        raise DomainInvariantError("project_id is required")

    return WorkbenchProjectClearTransition(
        project_id=project_id,
        cleared_at=cleared_at,
    )


__all__ = [
    "WorkbenchProjectClearTransition",
    "decide_workbench_project_clear_transition",
]
