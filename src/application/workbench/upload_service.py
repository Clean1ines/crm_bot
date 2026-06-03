from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchFreshUploadRepositoryPort,
)
from src.application.services.faq_workbench_fresh_upload_service import (
    FaqWorkbenchFreshUploadCommand,
    FaqWorkbenchFreshUploadResult,
    FaqWorkbenchFreshUploadService,
)
from src.application.workbench.dto import WorkbenchProcessDocumentJobPayloadDto
from src.domain.project_plane.knowledge_workbench import SourceType


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class WorkbenchUploadRepository(
    KnowledgeWorkbenchFreshUploadRepositoryPort,
    Protocol,
):
    pass


class WorkbenchProcessDocumentQueuePort(Protocol):
    async def enqueue_process_workbench_document(
        self,
        payload: WorkbenchProcessDocumentJobPayloadDto,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class FaqWorkbenchUploadCommand:
    project_id: str
    file_name: str
    upload_id: str
    raw_text: str
    file_size_bytes: int
    source_type: SourceType = SourceType.MARKDOWN
    content_hash: str | None = None
    uploaded_by_user_id: str | None = None
    uploaded_by_actor_type: str = "unknown"
    uploaded_by_actor_id: str | None = None
    trusted_upload: bool = False


@dataclass(frozen=True, slots=True)
class FaqWorkbenchUploadResult:
    upload: FaqWorkbenchFreshUploadResult
    queue_payload: WorkbenchProcessDocumentJobPayloadDto


class FaqWorkbenchUploadService:
    def __init__(
        self,
        repository: WorkbenchUploadRepository,
        queue: WorkbenchProcessDocumentQueuePort,
        *,
        id_factory: IdFactory,
    ) -> None:
        self._queue = queue
        self._fresh_upload_service = FaqWorkbenchFreshUploadService(
            repository,
            id_factory=id_factory,
        )

    async def upload_markdown(
        self,
        command: FaqWorkbenchUploadCommand,
    ) -> FaqWorkbenchUploadResult:
        upload = await self._fresh_upload_service.start_fresh_upload(
            FaqWorkbenchFreshUploadCommand(
                project_id=command.project_id,
                file_name=command.file_name,
                upload_id=command.upload_id,
                raw_text=command.raw_text,
                file_size_bytes=command.file_size_bytes,
                source_type=command.source_type,
                content_hash=command.content_hash,
                uploaded_by_user_id=command.uploaded_by_user_id,
                uploaded_by_actor_type=command.uploaded_by_actor_type,
                uploaded_by_actor_id=command.uploaded_by_actor_id,
                trusted_upload=command.trusted_upload,
            )
        )

        queue_payload = WorkbenchProcessDocumentJobPayloadDto.fresh_upload(
            project_id=upload.document.project_id,
            document_id=upload.document.document_id,
            processing_run_id=upload.processing_run.processing_run_id,
        )
        await self._queue.enqueue_process_workbench_document(queue_payload)

        return FaqWorkbenchUploadResult(
            upload=upload,
            queue_payload=queue_payload,
        )
