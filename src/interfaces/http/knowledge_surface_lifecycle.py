from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException

from src.application.dto.knowledge_dto import KnowledgeUploadJobPayloadDto
from src.application.ports.knowledge_port import (
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    PlatformUserAdminPort,
)
from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    PREPROCESSING_STATUS_PROCESSING,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_types import (
    TASK_PROCESS_KNOWLEDGE_UPLOAD,
    TASK_RETRY_KNOWLEDGE_FAILED_BATCHES,
)
from src.interfaces.http.dependencies import (
    get_pool,
    get_project_repo,
    get_queue_repo,
    get_user_repository,
)
from src.interfaces.http.knowledge import make_knowledge_repo
from src.interfaces.http.knowledge_surface import (
    _knowledge_service,
    router as surface_router,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])


def _retry_chunk_payload(chunk: SourceChunk) -> dict[str, object]:
    metadata = dict(chunk.metadata)
    return {
        "content": chunk.content,
        "section_body": chunk.content,
        "section_title": chunk.section_title,
        "title": chunk.section_title,
        "index": chunk.source_index,
        "page": chunk.page,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "source_refs": [
            {
                "source_chunk_id": chunk.id,
                "source_index": chunk.source_index,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
            }
        ],
        "metadata": metadata,
        "source_format": str(metadata.get("source_format") or ""),
        "semantic_unit_role_hint": str(metadata.get("semantic_unit_role_hint") or ""),
    }


async def _require_document(
    *,
    project_id: str,
    document_id: str,
    authorization: str | None,
    pool: asyncpg.Pool,
    project_repo: KnowledgeProjectAccessPort,
    user_repo: PlatformUserAdminPort,
):
    service = _knowledge_service(project_repo, user_repo, pool)
    await service.require_access(project_id, authorization)
    repo = KnowledgeRepository(pool)
    document = await repo.get_document(document_id)
    if document is None or document.project_id != project_id:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return service, repo, document


@router.get("/{document_id}/fragments", include_in_schema=False)
async def answer_drafts_surface_clean_break(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    service, _repo, document = await _require_document(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    if document.preprocessing_mode == MODE_FAQ:
        return {
            "document_id": document_id,
            "drafts": [],
            "total_count": 0,
            "blocked": True,
            "reason": "faq_uses_retrieval_surface_compilation",
        }

    result = await service.answer_drafts(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return result.to_dict()


@router.post("/{document_id}/retry-failed-batches", include_in_schema=False)
async def retry_knowledge_surface_lifecycle(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    queue_repo: KnowledgeQueuePort = Depends(get_queue_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    service, repo, document = await _require_document(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    user_id = await service.require_access(project_id, authorization)

    if document.preprocessing_mode != MODE_FAQ:
        return await service.retry_document_failed_batches(
            project_id,
            document_id,
            authorization,
            queue_repo=queue_repo,
            retry_failed_batches_task_type=TASK_RETRY_KNOWLEDGE_FAILED_BATCHES,
            logger=logger,
        )

    source_chunks = await repo.list_document_source_chunks(
        project_id=project_id,
        document_id=document_id,
    )
    if not source_chunks:
        raise HTTPException(
            status_code=409,
            detail="FAQ surface retry requires persisted source chunks",
        )

    await repo.update_document_status(document_id, "processing")
    await repo.update_document_preprocessing_status(
        document_id,
        mode=MODE_FAQ,
        status=PREPROCESSING_STATUS_PROCESSING,
        model="queued:GroqKnowledgeSurfaceCompiler",
        metrics={
            "stage": "faq_retrieval_surface_retry_queued",
            "status_message": "FAQ surface retry queued from persisted source chunks",
            "source_chunk_count": len(source_chunks),
            "bootstrap_fallback": False,
        },
    )

    job_id = await queue_repo.enqueue(
        TASK_PROCESS_KNOWLEDGE_UPLOAD,
        payload=KnowledgeUploadJobPayloadDto(
            project_id=project_id,
            document_id=document_id,
            file_name=document.file_name,
            preprocessing_mode=MODE_FAQ,
            chunks=[_retry_chunk_payload(chunk) for chunk in source_chunks],
        ).to_dict(),
        max_attempts=3,
    )

    logger.info(
        "FAQ surface retry queued",
        extra={
            "project_id": project_id,
            "document_id": document_id,
            "job_id": job_id,
            "requested_by": user_id,
        },
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "document_id": document_id,
        "preprocessing_mode": MODE_FAQ,
        "source": "faq_surface_retry",
    }


for lifecycle_route in reversed(router.routes):
    if lifecycle_route not in surface_router.routes:
        surface_router.routes.insert(0, lifecycle_route)


import src.interfaces.http.knowledge_surface_upload_guard  # noqa: E402,F401
