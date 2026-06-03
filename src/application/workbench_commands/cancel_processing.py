from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    KnowledgeDocument,
    KnowledgeProcessingRun,
    ProcessingLifecycleTransition,
    decide_processing_cancel_transition,
)


class WorkbenchCancelProcessingNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class WorkbenchCancelProcessingRejectedError(ValueError):
    reason: str
    project_id: str
    document_id: str

    def __str__(self) -> str:
        return (
            "Workbench cancel-processing rejected for document "
            f"{self.project_id}/{self.document_id}: {self.reason}"
        )


class WorkbenchCancelProcessingRepositoryPort(Protocol):
    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocument | None: ...

    async def get_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> KnowledgeProcessingRun | None: ...

    async def persist_processing_cancellation_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        transition: ProcessingLifecycleTransition,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class WorkbenchCancelProcessingCommand:
    project_id: str
    document_id: str


@dataclass(frozen=True, slots=True)
class WorkbenchCancelProcessingResult:
    project_id: str
    document_id: str
    processing_run_id: str
    status: str
    document_status: str
    processing_run_status: str
    resume_policy: str
    automatic_recovery_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "document_id": self.document_id,
            "processing_run_id": self.processing_run_id,
            "status": self.status,
            "document_status": self.document_status,
            "processing_run_status": self.processing_run_status,
            "resume_policy": self.resume_policy,
            "automatic_recovery_allowed": self.automatic_recovery_allowed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchCancelProcessingService:
    repository: WorkbenchCancelProcessingRepositoryPort

    async def cancel_processing(
        self,
        command: WorkbenchCancelProcessingCommand,
    ) -> WorkbenchCancelProcessingResult:
        document = await self.repository.get_document(
            project_id=command.project_id,
            document_id=command.document_id,
        )
        if document is None:
            raise WorkbenchCancelProcessingNotFoundError("Knowledge document not found")

        processing_run_id = str(document.current_processing_run_id or "").strip()
        if not processing_run_id:
            raise WorkbenchCancelProcessingRejectedError(
                reason="document has no current processing run to cancel",
                project_id=command.project_id,
                document_id=command.document_id,
            )

        existing_run = await self.repository.get_processing_run(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
        )
        if existing_run is None:
            raise WorkbenchCancelProcessingRejectedError(
                reason="current processing run record was not found",
                project_id=command.project_id,
                document_id=command.document_id,
            )

        transition = decide_processing_cancel_transition(
            document=document,
            existing_run=existing_run,
        )
        if not transition.may_proceed:
            raise WorkbenchCancelProcessingRejectedError(
                reason=transition.reason,
                project_id=command.project_id,
                document_id=command.document_id,
            )
        if transition.document_status_after is None:
            raise WorkbenchCancelProcessingRejectedError(
                reason="cancellation transition missing document status",
                project_id=command.project_id,
                document_id=command.document_id,
            )
        if transition.processing_run_status_after is None:
            raise WorkbenchCancelProcessingRejectedError(
                reason="cancellation transition missing processing run status",
                project_id=command.project_id,
                document_id=command.document_id,
            )

        await self.repository.persist_processing_cancellation_transition(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
            transition=transition,
        )

        return WorkbenchCancelProcessingResult(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
            status="cancelled",
            document_status=transition.document_status_after.value,
            processing_run_status=transition.processing_run_status_after.value,
            resume_policy=transition.resume_policy_after.value,
            automatic_recovery_allowed=transition.automatic_recovery_allowed_after,
            reason=transition.reason,
        )


__all__ = [
    "WorkbenchCancelProcessingCommand",
    "WorkbenchCancelProcessingNotFoundError",
    "WorkbenchCancelProcessingRejectedError",
    "WorkbenchCancelProcessingResult",
    "WorkbenchCancelProcessingService",
]
