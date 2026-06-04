from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, cast

from src.domain.project_plane.knowledge_workbench.deletion import (
    WorkbenchDeleteDocument,
    WorkbenchDeleteProcessingRun,
    WorkbenchDocumentDeleteTransition,
    decide_workbench_document_delete_transition,
)
from src.domain.project_plane.knowledge_workbench.errors import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)


class WorkbenchDocumentDeleteNotFoundError(LookupError):
    pass


class WorkbenchDocumentDeleteRejectedError(ValueError):
    pass


class WorkbenchDocumentDeleteRepositoryPort(Protocol):
    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> object | None: ...

    async def get_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> object | None: ...

    async def persist_document_delete_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        current_processing_run_id: str | None,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus | None,
        deleted_at: datetime,
    ) -> None: ...

    async def cleanup_document_final_retrieval_projections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentDeleteCommand:
    project_id: str
    document_id: str

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise WorkbenchDocumentDeleteRejectedError("project_id is required")
        if not self.document_id.strip():
            raise WorkbenchDocumentDeleteRejectedError("document_id is required")


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentDeleteResult:
    project_id: str
    document_id: str
    deleted_at: datetime
    document_status: KnowledgeDocumentStatus
    current_processing_run_id: str | None
    processing_run_status: ProcessingRunStatus | None
    pending_queue_jobs_removed: bool
    runtime_publication_removed: bool

    @classmethod
    def from_transition(
        cls,
        transition: WorkbenchDocumentDeleteTransition,
    ) -> WorkbenchDocumentDeleteResult:
        return cls(
            project_id=transition.project_id,
            document_id=transition.document_id,
            deleted_at=transition.deleted_at,
            document_status=transition.document_status_after,
            current_processing_run_id=transition.processing_run_id,
            processing_run_status=transition.processing_run_status_after,
            pending_queue_jobs_removed=transition.pending_queue_jobs_should_be_removed,
            runtime_publication_removed=(
                transition.runtime_publication_should_be_removed
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "deleted",
            "project_id": self.project_id,
            "document_id": self.document_id,
            "deleted_at": self.deleted_at.isoformat(),
            "document_status": self.document_status.value,
            "current_processing_run_id": self.current_processing_run_id,
            "processing_run_status": (
                self.processing_run_status.value
                if self.processing_run_status is not None
                else None
            ),
            "pending_queue_jobs_removed": self.pending_queue_jobs_removed,
            "runtime_publication_removed": self.runtime_publication_removed,
        }


class WorkbenchDocumentDeleteService:
    def __init__(self, repository: WorkbenchDocumentDeleteRepositoryPort) -> None:
        self._repository = repository

    async def delete_document(
        self,
        command: WorkbenchDocumentDeleteCommand,
    ) -> WorkbenchDocumentDeleteResult:
        document = await self._repository.get_document(
            project_id=command.project_id,
            document_id=command.document_id,
        )
        if document is None:
            raise WorkbenchDocumentDeleteNotFoundError("Knowledge document not found")

        processing_run_id = str(
            getattr(document, "current_processing_run_id", "") or ""
        ).strip()
        current_processing_run = None
        if processing_run_id:
            current_processing_run = await self._repository.get_processing_run(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=processing_run_id,
            )
            if current_processing_run is None:
                raise WorkbenchDocumentDeleteRejectedError(
                    "current processing run is missing"
                )

        try:
            transition = decide_workbench_document_delete_transition(
                document=cast(WorkbenchDeleteDocument, document),
                current_processing_run=cast(
                    WorkbenchDeleteProcessingRun | None,
                    current_processing_run,
                ),
                deleted_at=datetime.now(timezone.utc),
            )
        except DomainInvariantError as exc:
            raise WorkbenchDocumentDeleteRejectedError(str(exc)) from exc

        await self._repository.persist_document_delete_transition(
            project_id=transition.project_id,
            document_id=transition.document_id,
            current_processing_run_id=transition.processing_run_id,
            document_status=transition.document_status_after,
            processing_run_status=transition.processing_run_status_after,
            deleted_at=transition.deleted_at,
        )
        if transition.runtime_publication_should_be_removed:
            await self._repository.cleanup_document_final_retrieval_projections(
                project_id=transition.project_id,
                document_id=transition.document_id,
            )
        return WorkbenchDocumentDeleteResult.from_transition(transition)


__all__ = [
    "WorkbenchDocumentDeleteCommand",
    "WorkbenchDocumentDeleteNotFoundError",
    "WorkbenchDocumentDeleteRejectedError",
    "WorkbenchDocumentDeleteResult",
    "WorkbenchDocumentDeleteService",
]
