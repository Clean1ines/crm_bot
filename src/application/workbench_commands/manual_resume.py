from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.workbench.dto import WorkbenchProcessDocumentJobPayloadDto
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    KnowledgeDocument,
    KnowledgeProcessingRun,
    ProcessingTrigger,
    decide_processing_lifecycle,
)


class WorkbenchManualResumeNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class WorkbenchManualResumeRejectedError(ValueError):
    reason: str
    document_id: str
    processing_run_id: str | None = None

    def __str__(self) -> str:
        if self.processing_run_id:
            return (
                "Workbench manual resume rejected for document "
                f"{self.document_id} / run {self.processing_run_id}: {self.reason}"
            )
        return f"Workbench manual resume rejected for document {self.document_id}: {self.reason}"


class WorkbenchManualResumeRepositoryPort(Protocol):
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

    async def persist_processing_manual_resume_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None: ...


class WorkbenchManualResumeQueuePort(Protocol):
    async def enqueue_process_workbench_document(
        self,
        payload: WorkbenchProcessDocumentJobPayloadDto,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class WorkbenchManualResumeCommand:
    project_id: str
    document_id: str


@dataclass(frozen=True, slots=True)
class WorkbenchManualResumeResult:
    project_id: str
    document_id: str
    processing_run_id: str
    status: str
    source: str
    resume_policy: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "document_id": self.document_id,
            "processing_run_id": self.processing_run_id,
            "status": self.status,
            "source": self.source,
            "resume_policy": self.resume_policy,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchManualResumeService:
    repository: WorkbenchManualResumeRepositoryPort
    queue: WorkbenchManualResumeQueuePort

    async def resume_document(
        self,
        command: WorkbenchManualResumeCommand,
    ) -> WorkbenchManualResumeResult:
        document = await self.repository.get_document(
            project_id=command.project_id,
            document_id=command.document_id,
        )
        if document is None:
            raise WorkbenchManualResumeNotFoundError("Knowledge document not found")

        processing_run_id = document.current_processing_run_id
        if not processing_run_id:
            raise WorkbenchManualResumeRejectedError(
                reason="document has no current processing run to resume",
                document_id=command.document_id,
            )

        existing_run = await self.repository.get_processing_run(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
        )

        try:
            decision = decide_processing_lifecycle(
                trigger=ProcessingTrigger.EXPLICIT_USER_RESUME,
                document=document,
                requested_processing_run_id=processing_run_id,
                existing_run=existing_run,
            )
        except DomainInvariantError as exc:
            raise WorkbenchManualResumeRejectedError(
                reason=str(exc),
                document_id=command.document_id,
                processing_run_id=processing_run_id,
            ) from exc

        if not decision.may_resume:
            raise WorkbenchManualResumeRejectedError(
                reason=decision.reason,
                document_id=command.document_id,
                processing_run_id=processing_run_id,
            )

        await self.repository.persist_processing_manual_resume_transition(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
        )

        payload = WorkbenchProcessDocumentJobPayloadDto.explicit_user_resume(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
        )
        await self.queue.enqueue_process_workbench_document(payload)

        return WorkbenchManualResumeResult(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=processing_run_id,
            status="queued",
            source=payload.source.value,
            resume_policy=decision.resume_policy.value,
            reason=decision.reason,
        )


__all__ = [
    "WorkbenchManualResumeCommand",
    "WorkbenchManualResumeNotFoundError",
    "WorkbenchManualResumeRejectedError",
    "WorkbenchManualResumeResult",
    "WorkbenchManualResumeService",
]
