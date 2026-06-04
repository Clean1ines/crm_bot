from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, cast
from uuid import uuid4

import asyncpg

from src.application.ports.logger_port import LoggerPort
from src.application.workbench.upload_service import (
    FaqWorkbenchUploadCommand,
    FaqWorkbenchUploadService,
)
from src.domain.project_plane.knowledge_workbench import SourceType
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)
from src.infrastructure.llm.chunker import ChunkerService
from src.infrastructure.queue.workbench_parallel_queue import (
    WorkbenchParallelQueueAdapter,
    WorkbenchParallelQueueConnection,
)


MODE_FAQ = "faq"
PREPROCESSING_STATUS_PROCESSING = "processing"


@dataclass(frozen=True, slots=True)
class FaqWorkbenchKnowledgeUploadResult:
    message: str
    chunks: int
    document_id: str | None = None
    preprocessing_mode: str = MODE_FAQ
    preprocessing_status: str | None = None
    structured_entries: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "message": self.message,
            "chunks": self.chunks,
            "document_id": self.document_id,
            "preprocessing_mode": self.preprocessing_mode,
            "preprocessing_status": self.preprocessing_status,
            "structured_entries": self.structured_entries,
        }


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)


class UuidIdFactory:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4()}"


def _source_part_text(part: object) -> str:
    if isinstance(part, str):
        return part.strip()

    if not isinstance(part, Mapping):
        return ""

    for key in ("content", "text", "raw_text", "section_body", "body"):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


async def extract_workbench_raw_text(
    *,
    file_content: bytes | bytearray,
    file_name: str,
    logger: LoggerPort,
) -> str:
    extractor = ChunkerService()
    source_parts = await extractor.process_file(file_content, file_name)
    raw_text = "\n\n".join(
        text for part in source_parts if (text := _source_part_text(part))
    ).strip()
    if not raw_text:
        logger.warning("No text extracted from FAQ Workbench upload")
    return raw_text


async def upload_faq_workbench_knowledge_file(
    *,
    pool: object,
    queue_repo: object,
    project_id: str,
    file_name: str | None,
    file_content: bytes | bytearray,
    logger: LoggerPort,
    uploaded_by_user_id: str | None = None,
    uploaded_by_actor_type: str = "unknown",
    uploaded_by_actor_id: str | None = None,
    trusted_upload: bool = False,
) -> FaqWorkbenchKnowledgeUploadResult:
    normalized_file_name = file_name or "upload"
    raw_text = await extract_workbench_raw_text(
        file_content=file_content,
        file_name=normalized_file_name,
        logger=logger,
    )
    if not raw_text:
        return FaqWorkbenchKnowledgeUploadResult(
            message="No text extracted",
            chunks=0,
            preprocessing_status=None,
            structured_entries=0,
        )

    upload_service = FaqWorkbenchUploadService(
        _workbench_repository(cast(asyncpg.Pool, pool)),
        WorkbenchParallelQueueAdapter(
            connection=cast(WorkbenchParallelQueueConnection, queue_repo),
        ),
        id_factory=UuidIdFactory(),
    )
    result = await upload_service.upload_markdown(
        FaqWorkbenchUploadCommand(
            project_id=project_id,
            file_name=normalized_file_name,
            upload_id=f"upload-{uuid4()}",
            raw_text=raw_text,
            file_size_bytes=len(file_content),
            source_type=SourceType.MARKDOWN,
            content_hash=sha256(bytes(file_content)).hexdigest(),
            uploaded_by_user_id=uploaded_by_user_id,
            uploaded_by_actor_type=uploaded_by_actor_type,
            uploaded_by_actor_id=uploaded_by_actor_id,
            trusted_upload=trusted_upload,
        )
    )

    section_count = len(result.upload.sections)
    return FaqWorkbenchKnowledgeUploadResult(
        message=f"Queued {section_count} workbench sections for processing",
        chunks=section_count,
        document_id=result.upload.document.document_id,
        preprocessing_status=PREPROCESSING_STATUS_PROCESSING,
        structured_entries=0,
    )
