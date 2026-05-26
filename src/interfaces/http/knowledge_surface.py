from __future__ import annotations

import uuid

import asyncpg
from collections.abc import Sequence

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from src.application.dto.knowledge_dto import (
    KnowledgeUploadJobPayloadDto,
    KnowledgeUploadRequestDto,
    KnowledgeUploadResultDto,
    SurfacePublishResponseDto,
)
from src.application.errors import ValidationError
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    PlatformUserAdminPort,
)
from src.application.services.knowledge_service import (
    KnowledgeService,
    KnowledgeServiceConfig,
)
from src.domain.project_plane.embedding_text import CANONICAL_EMBEDDING_TEXT_VERSION
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    EmbeddingText,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    MODE_PLAIN,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
    normalize_preprocessing_mode,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceDraft,
    SurfaceQuestionOwnership,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.llm.knowledge_surface_compiler import (
    FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
)
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_types import TASK_PROCESS_KNOWLEDGE_UPLOAD
from src.interfaces.http.dependencies import (
    get_pool,
    get_project_repo,
    get_queue_repo,
    get_user_repository,
)
from src.interfaces.http.knowledge import (
    jwt_decoder,
    make_chunker,
    make_knowledge_preprocessor,
    make_knowledge_repo,
    _read_upload_bytes,
)
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)
router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])


def _knowledge_service(
    project_repo: KnowledgeProjectAccessPort,
    user_repo: PlatformUserAdminPort,
    pool: KnowledgeDbPoolPort,
) -> KnowledgeService:
    return KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )


@router.post("")
async def upload_knowledge_surface_aware(
    project_id: str,
    file: UploadFile = File(...),
    preprocessing_mode: str = Form(default="plain"),
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    queue_repo: KnowledgeQueuePort = Depends(get_queue_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    """Upload knowledge with FAQ routed to Retrieval Surface Compilation.

    This route is included before the legacy knowledge router and therefore
    prevents FAQ uploads from being wired through the old flat preprocessor
    factory. Non-FAQ legacy modes are delegated unchanged.
    """
    try:
        mode = normalize_preprocessing_mode(preprocessing_mode)
    except KnowledgePreprocessingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = _knowledge_service(project_repo, user_repo, pool)
    if mode != MODE_FAQ:
        file_content = await _read_upload_bytes(file)
        result = await service.upload(
            project_id,
            file.filename,
            file_content,
            authorization,
            chunker_factory=make_chunker,
            knowledge_repo_factory=make_knowledge_repo,
            logger=logger,
            queue_repo=queue_repo,
            knowledge_upload_task_type=TASK_PROCESS_KNOWLEDGE_UPLOAD,
            upload_request=KnowledgeUploadRequestDto(preprocessing_mode=mode),
            preprocessor_factory=(
                lambda: make_knowledge_preprocessor(preprocessing_mode=mode)
            ),
        )
        return result.to_dict()

    file_content = await _read_upload_bytes(file)
    user_id = await service.require_access(project_id, authorization)
    await service._ensure_project_exists(project_id, logger)
    file_name = file.filename or "upload"
    chunks = await service._extract_chunks(
        file_content,
        file_name,
        chunker_factory=make_chunker,
        logger=logger,
    )
    if not chunks:
        return KnowledgeUploadResultDto.create(
            message="No text extracted", chunks=0
        ).to_dict()

    repo = KnowledgeRepository(pool)
    document_id = await repo.create_document(
        project_id=project_id,
        file_name=file_name,
        file_size=len(file_content),
        uploaded_by=user_id,
    )
    await repo.update_document_status(document_id, "processing")
    await repo.update_document_preprocessing_status(
        document_id,
        mode=MODE_FAQ,
        status=PREPROCESSING_STATUS_PROCESSING,
        model="queued:GroqKnowledgeSurfaceCompiler",
        prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
        metrics={
            "stage": "queued",
            "surface_compiler_factory": "GroqKnowledgeSurfaceCompiler",
            "preprocessor_factory": None,
            "bootstrap_fallback": False,
        },
    )
    await queue_repo.enqueue(
        TASK_PROCESS_KNOWLEDGE_UPLOAD,
        payload=KnowledgeUploadJobPayloadDto(
            project_id=project_id,
            document_id=document_id,
            file_name=file_name,
            preprocessing_mode=MODE_FAQ,
            chunks=chunks,
        ).to_dict(),
    )
    preprocessing_status = (
        PREPROCESSING_STATUS_NOT_REQUESTED
        if mode == MODE_PLAIN
        else PREPROCESSING_STATUS_PROCESSING
    )
    return KnowledgeUploadResultDto.create(
        message=f"Queued {len(chunks)} chunks for FAQ surface compilation",
        chunks=len(chunks),
        document_id=document_id,
        preprocessing_mode=MODE_FAQ,
        preprocessing_status=preprocessing_status,
        structured_entries=0,
    ).to_dict()


def _surface_source_indexes(surface: RetrievalSurfaceDraft) -> tuple[int, ...]:
    if surface.source_chunk_indexes:
        return surface.source_chunk_indexes
    indexes: list[int] = []
    for ref in surface.source_refs:
        parts = ref.split(":")
        if len(parts) >= 2 and parts[0] == "chunk" and parts[1].isdigit():
            value = int(parts[1])
            if value not in indexes:
                indexes.append(value)
    return tuple(indexes)


def _surface_source_refs(
    surface: RetrievalSurfaceDraft,
    source_chunks: Sequence[SourceChunk],
) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    indexes = _surface_source_indexes(surface)
    chunks_by_index = {chunk.source_index: chunk for chunk in source_chunks}
    for source_index in indexes:
        chunk = chunks_by_index.get(source_index)
        if chunk is None:
            continue
        quote = (
            surface.source_excerpt.strip() or surface.answer.strip() or chunk.content
        )
        refs.append(
            SourceRef(
                source_index=chunk.source_index,
                quote=quote,
                source_chunk_id=chunk.id,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                confidence=surface.confidence,
            )
        )
    if refs:
        return tuple(refs)
    if not source_chunks:
        return ()
    fallback = source_chunks[0]
    return (
        SourceRef(
            source_index=fallback.source_index,
            quote=surface.source_excerpt.strip() or fallback.content,
            source_chunk_id=fallback.id,
            start_offset=fallback.start_offset,
            end_offset=fallback.end_offset,
            confidence=surface.confidence,
        ),
    )


def _owned_questions(
    surface: RetrievalSurfaceDraft,
    ownership: Sequence[SurfaceQuestionOwnership],
) -> tuple[str, ...]:
    result: list[str] = []
    for question in (surface.canonical_question, surface.title):
        cleaned = " ".join(question.strip().split())
        if cleaned and cleaned not in result:
            result.append(cleaned)
    for item in ownership:
        if item.owner_surface_key != surface.local_surface_key:
            continue
        if item.question_kind == "expected_topic_hint":
            continue
        cleaned = " ".join(item.question.strip().split())
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _embedding_text(
    *,
    surface: RetrievalSurfaceDraft,
    questions: Sequence[str],
) -> str:
    parts = (
        surface.title,
        surface.canonical_question,
        " ".join(questions),
        surface.short_answer,
        surface.answer,
        surface.answer_scope,
        surface.question_scope,
        surface.exclusion_scope,
    )
    return " ".join(part.strip() for part in parts if part and part.strip())


def _canonical_entry_from_surface(
    *,
    project_id: str,
    document_id: str,
    surface: RetrievalSurfaceDraft,
    source_refs: tuple[SourceRef, ...],
    ownership: Sequence[SurfaceQuestionOwnership],
) -> CanonicalKnowledgeEntry:
    stable_key = f"{document_id}:faq_surface:{surface.local_surface_key}"
    entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
    questions = _owned_questions(surface, ownership)
    entry = CanonicalKnowledgeEntry(
        id=entry_id,
        project_id=project_id,
        document_id=document_id,
        compiler_run_id="",
        stable_key=stable_key,
        entry_kind=KnowledgeEntryKind.FAQ_ANSWER,
        title=surface.title,
        answer=surface.answer,
        source_refs=source_refs,
        enrichment=KnowledgeEnrichment(
            questions=questions,
            tags=(surface.surface_kind,),
            retrieval_guards=(surface.exclusion_scope,)
            if surface.exclusion_scope
            else (),
        ),
        embedding_text=EmbeddingText(
            value=_embedding_text(surface=surface, questions=questions),
            version=CANONICAL_EMBEDDING_TEXT_VERSION,
        ),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
        version=1,
        compiler_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
        embedding_text_version=CANONICAL_EMBEDDING_TEXT_VERSION,
        metadata={
            "publication_source": "faq_retrieval_surface",
            "surface_id": surface.id,
            "surface_key": surface.local_surface_key,
            "surface_kind": surface.surface_kind,
            "surface_run_id": surface.run_id,
            "owned_question_count": len(questions),
        },
    )
    entry.assert_publishable()
    return entry


async def _link_surface_to_canonical_entry(
    *,
    pool: asyncpg.Pool,
    surface_id: str,
    entry_id: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE knowledge_surfaces
            SET linked_canonical_entry_id = $2::uuid,
                updated_at = now()
            WHERE id = $1::uuid
            """,
            ensure_uuid(surface_id),
            ensure_uuid(entry_id),
        )


@router.post("/{document_id}/surfaces/{surface_id}/publish")
async def publish_surface_to_runtime_entry(
    project_id: str,
    document_id: str,
    surface_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    service = _knowledge_service(project_repo, user_repo, pool)
    await service.require_access(project_id, authorization)

    repo = KnowledgeRepository(pool)
    document = await repo.get_document(document_id)
    if document is None or document.project_id != project_id:
        raise HTTPException(status_code=404, detail="Knowledge document not found")

    surface = await repo.get_surface_by_id(surface_id=surface_id)
    if surface is None:
        raise HTTPException(status_code=404, detail="Surface not found")
    if surface.document_id != document_id:
        raise HTTPException(
            status_code=400, detail="Surface does not belong to document"
        )
    if surface.linked_runtime_entry_id is not None:
        await repo.update_surface_publication_status(
            surface_id=surface_id,
            publication_status="published",
        )
        return SurfacePublishResponseDto(
            surface_id=surface_id,
            publication_status="published",
            linked_runtime_entry_id=surface.linked_runtime_entry_id,
        )

    await repo.update_surface_publication_status(
        surface_id=surface_id,
        publication_status="publishing",
    )
    try:
        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        source_refs = _surface_source_refs(surface, source_chunks)
        if not source_refs:
            raise ValidationError("Surface has no source refs")
        ownership = await repo.list_surface_ownership_for_run(run_id=surface.run_id)
        entry = _canonical_entry_from_surface(
            project_id=project_id,
            document_id=document_id,
            surface=surface,
            source_refs=source_refs,
            ownership=ownership,
        )
        await repo.add_canonical_entries(
            project_id=project_id,
            document_id=document_id,
            entries=(entry,),
        )
        await repo.link_surface_to_runtime_entry(
            surface_id=surface_id,
            runtime_entry_id=entry.id,
        )
        await _link_surface_to_canonical_entry(
            pool=pool,
            surface_id=surface_id,
            entry_id=entry.id,
        )
        await repo.update_surface_publication_status(
            surface_id=surface_id,
            publication_status="published",
        )
        return SurfacePublishResponseDto(
            surface_id=surface_id,
            publication_status="published",
            linked_runtime_entry_id=entry.id,
        )
    except Exception as exc:
        await repo.update_surface_publication_status(
            surface_id=surface_id,
            publication_status="publish_failed",
        )
        raise HTTPException(
            status_code=409,
            detail=str(exc)[:300] or type(exc).__name__,
        ) from exc
