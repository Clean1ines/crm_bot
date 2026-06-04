from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.domain.project_plane.knowledge_workbench.errors import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)
from src.domain.project_plane.knowledge_workbench.project_clear import (
    WorkbenchProjectClearTransition,
    decide_workbench_project_clear_transition,
)


class WorkbenchProjectClearRejectedError(ValueError):
    pass


class WorkbenchProjectClearRepositoryPort(Protocol):
    async def persist_project_clear_transition(
        self,
        *,
        project_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        cleared_at: datetime,
    ) -> int: ...

    async def cleanup_project_final_retrieval_projections(
        self,
        *,
        project_id: str,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class WorkbenchProjectClearCommand:
    project_id: str

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise WorkbenchProjectClearRejectedError("project_id is required")


@dataclass(frozen=True, slots=True)
class WorkbenchProjectClearResult:
    project_id: str
    cleared_at: datetime
    document_status: KnowledgeDocumentStatus
    processing_run_status: ProcessingRunStatus
    affected_documents: int
    pending_queue_jobs_removed: bool
    runtime_publications_removed: bool

    @classmethod
    def from_transition(
        cls,
        transition: WorkbenchProjectClearTransition,
        *,
        affected_documents: int,
    ) -> WorkbenchProjectClearResult:
        return cls(
            project_id=transition.project_id,
            cleared_at=transition.cleared_at,
            document_status=transition.document_status_after,
            processing_run_status=transition.processing_run_status_after,
            affected_documents=affected_documents,
            pending_queue_jobs_removed=transition.pending_queue_jobs_should_be_removed,
            runtime_publications_removed=(
                transition.runtime_publications_should_be_removed
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "cleared",
            "project_id": self.project_id,
            "cleared_at": self.cleared_at.isoformat(),
            "document_status": self.document_status.value,
            "processing_run_status": self.processing_run_status.value,
            "affected_documents": self.affected_documents,
            "pending_queue_jobs_removed": self.pending_queue_jobs_removed,
            "runtime_publications_removed": self.runtime_publications_removed,
        }


class WorkbenchProjectClearService:
    def __init__(self, repository: WorkbenchProjectClearRepositoryPort) -> None:
        self._repository = repository

    async def clear_project(
        self,
        command: WorkbenchProjectClearCommand,
    ) -> WorkbenchProjectClearResult:
        try:
            transition = decide_workbench_project_clear_transition(
                project_id=command.project_id,
                cleared_at=datetime.now(timezone.utc),
            )
        except DomainInvariantError as exc:
            raise WorkbenchProjectClearRejectedError(str(exc)) from exc

        affected_documents = await self._repository.persist_project_clear_transition(
            project_id=transition.project_id,
            document_status=transition.document_status_after,
            processing_run_status=transition.processing_run_status_after,
            cleared_at=transition.cleared_at,
        )
        if transition.runtime_publications_should_be_removed:
            await self._repository.cleanup_project_final_retrieval_projections(
                project_id=transition.project_id,
            )
        return WorkbenchProjectClearResult.from_transition(
            transition,
            affected_documents=affected_documents,
        )


__all__ = [
    "WorkbenchProjectClearCommand",
    "WorkbenchProjectClearRejectedError",
    "WorkbenchProjectClearResult",
    "WorkbenchProjectClearService",
]
