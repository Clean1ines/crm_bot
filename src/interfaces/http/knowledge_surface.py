from __future__ import annotations

import uuid
from datetime import datetime

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
    RetrievalSurfaceCompilerRun,
    RetrievalSurfaceCompilerStage,
    RetrievalSurfaceDraft,
    RetrievalSurfaceMergeDecision,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceUnit,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
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


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _require_document_access(
    *,
    project_id: str,
    document_id: str,
    authorization: str | None,
    pool: asyncpg.Pool,
    project_repo: KnowledgeProjectAccessPort,
    user_repo: PlatformUserAdminPort,
) -> KnowledgeRepository:
    service = _knowledge_service(project_repo, user_repo, pool)
    await service.require_access(project_id, authorization)
    repo = KnowledgeRepository(pool)
    document = await repo.get_document(document_id)
    if document is None or document.project_id != project_id:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return repo


def _run_payload(run: RetrievalSurfaceCompilerRun) -> dict[str, object]:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "document_id": run.document_id,
        "mode": run.mode,
        "status": run.status,
        "compiler_kind": run.compiler_kind,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "started_at": _timestamp(run.started_at),
        "completed_at": _timestamp(run.completed_at),
        "error_type": run.error_type,
        "error_message": run.error_message,
        "metrics": run.metrics,
    }


def _stage_payload(stage: RetrievalSurfaceCompilerStage) -> dict[str, object]:
    return {
        "id": stage.id,
        "run_id": stage.run_id,
        "document_id": stage.document_id,
        "stage_kind": stage.stage_kind,
        "status": stage.status,
        "model": stage.model,
        "prompt_version": stage.prompt_version,
        "input_summary": stage.input_summary,
        "output_summary": stage.output_summary,
        "tokens_input": stage.tokens_input,
        "tokens_output": stage.tokens_output,
        "tokens_total": stage.tokens_total,
        "error_type": stage.error_type,
        "error_message": stage.error_message,
        "started_at": _timestamp(stage.started_at),
        "completed_at": _timestamp(stage.completed_at),
        "metrics": stage.metrics,
    }


def _source_unit_payload(unit: RetrievalSurfaceSourceUnit) -> dict[str, object]:
    return {
        "id": unit.id,
        "run_id": unit.run_id,
        "document_id": unit.document_id,
        "source_unit_key": unit.source_unit_key,
        "source_chunk_indexes": list(unit.source_chunk_indexes),
        "title": unit.title,
        "body": unit.body,
        "children": [
            {
                "title": child.title,
                "body": child.body,
                "raw_text": child.raw_text,
                "label_kind": child.label_kind,
                "metadata": child.metadata,
            }
            for child in unit.children
        ],
        "raw_text": unit.raw_text,
        "section_path": list(unit.section_path),
        "source_refs": list(unit.source_refs),
        "preprocessing_mode": unit.preprocessing_mode,
        "metadata": unit.metadata,
    }


def _relation_payload(relation: RetrievalSurfaceRelation) -> dict[str, object]:
    return {
        "id": relation.id,
        "run_id": relation.run_id,
        "document_id": relation.document_id,
        "parent_surface_key": relation.parent_surface_key,
        "child_surface_key": relation.child_surface_key,
        "relation_type": relation.relation_type,
        "reason": relation.reason,
        "confidence": relation.confidence,
        "source_refs": list(relation.source_refs),
    }


def _ownership_payload(item: SurfaceQuestionOwnership) -> dict[str, object]:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "document_id": item.document_id,
        "question": item.question,
        "owner_surface_key": item.owner_surface_key,
        "question_kind": item.question_kind,
        "confidence": item.confidence,
        "reason": item.reason,
        "rejected_from_surface_keys": list(item.rejected_from_surface_keys),
    }


def _reassignment_payload(item: SurfaceQuestionReassignment) -> dict[str, object]:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "document_id": item.document_id,
        "question": item.question,
        "from_surface_key": item.from_surface_key,
        "to_surface_key": item.to_surface_key,
        "reason": item.reason,
        "confidence": item.confidence,
    }


def _merge_decision_payload(item: RetrievalSurfaceMergeDecision) -> dict[str, object]:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "document_id": item.document_id,
        "survivor_surface_key": item.survivor_surface_key,
        "merged_surface_keys": list(item.merged_surface_keys),
        "keep_separate_surface_keys": list(item.keep_separate_surface_keys),
        "decision_type": item.decision_type,
        "reason": item.reason,
        "confidence": item.confidence,
    }


def _surface_payload(
    surface: RetrievalSurfaceDraft,
    *,
    ownership: Sequence[SurfaceQuestionOwnership] = (),
    reassignments: Sequence[SurfaceQuestionReassignment] = (),
    relations: Sequence[RetrievalSurfaceRelation] = (),
    merge_decisions: Sequence[RetrievalSurfaceMergeDecision] = (),
) -> dict[str, object]:
    surface_key = surface.local_surface_key
    owned_questions = [
        _ownership_payload(item)
        for item in ownership
        if item.owner_surface_key == surface_key
    ]
    rejected_questions = [
        _ownership_payload(item)
        for item in ownership
        if surface_key in item.rejected_from_surface_keys
    ]
    incoming_reassignments = [
        _reassignment_payload(item)
        for item in reassignments
        if item.to_surface_key == surface_key
    ]
    outgoing_reassignments = [
        _reassignment_payload(item)
        for item in reassignments
        if item.from_surface_key == surface_key
    ]
    surface_relations = [
        _relation_payload(item)
        for item in relations
        if item.parent_surface_key == surface_key or item.child_surface_key == surface_key
    ]
    surface_merge_decisions = [
        _merge_decision_payload(item)
        for item in merge_decisions
        if item.survivor_surface_key == surface_key
        or surface_key in item.merged_surface_keys
        or surface_key in item.keep_separate_surface_keys
    ]
    return {
        "id": surface.id,
        "run_id": surface.run_id,
        "document_id": surface.document_id,
        "surface_key": surface.local_surface_key,
        "local_surface_key": surface.local_surface_key,
        "surface_kind": surface.surface_kind,
        "title": surface.title,
        "canonical_question": surface.canonical_question,
        "answer": surface.answer,
        "short_answer": surface.short_answer,
        "answer_scope": surface.answer_scope,
        "question_scope": surface.question_scope,
        "exclusion_scope": surface.exclusion_scope,
        "status": surface.status,
        "publication_status": surface.publication_status,
        "source_refs": list(surface.source_refs),
        "source_excerpt": surface.source_excerpt,
        "source_chunk_indexes": list(surface.source_chunk_indexes),
        "confidence": surface.confidence,
        "warnings": list(surface.warnings),
        "metadata": surface.metadata,
        "parent_surface_keys": [
            item.parent_surface_key
            for item in relations
            if item.child_surface_key == surface_key
        ],
        "child_surface_keys": [
            item.child_surface_key
            for item in relations
            if item.parent_surface_key == surface_key
        ],
        "owned_questions": owned_questions,
        "rejected_questions": rejected_questions,
        "incoming_reassignments": incoming_reassignments,
        "outgoing_reassignments": outgoing_reassignments,
        "relations": surface_relations,
        "merge_decisions": surface_merge_decisions,
        "linked_candidate_id": surface.linked_candidate_id,
        "linked_canonical_entry_id": surface.linked_canonical_entry_id,
        "linked_runtime_entry_id": surface.linked_runtime_entry_id,
    }


async def _latest_surface_run(
    repo: KnowledgeRepository,
    *,
    project_id: str,
    document_id: str,
) -> RetrievalSurfaceCompilerRun | None:
    return await repo.get_latest_surface_run_for_document(
        project_id=project_id,
        document_id=document_id,
    )


@router.get("/{document_id}/surface-compilation")
async def get_surface_compilation_state(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    repo = await _require_document_access(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    run = await _latest_surface_run(repo, project_id=project_id, document_id=document_id)
    if run is None:
        return {"run": None, "stages": [], "source_units": []}
    stages = await repo.list_surface_stages_for_run(run_id=run.id)
    source_units = await repo.list_surface_source_units_for_run(run_id=run.id)
    return {
        "run": _run_payload(run),
        "stages": [_stage_payload(stage) for stage in stages],
        "source_units": [_source_unit_payload(unit) for unit in source_units],
    }


@router.get("/{document_id}/surfaces")
async def list_document_surfaces(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    repo = await _require_document_access(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    run = await _latest_surface_run(repo, project_id=project_id, document_id=document_id)
    if run is None:
        return {"surfaces": []}
    surfaces = await repo.list_surfaces_for_run(run_id=run.id)
    ownership = await repo.list_surface_ownership_for_run(run_id=run.id)
    reassignments = await repo.list_surface_reassignments_for_run(run_id=run.id)
    relations = await repo.list_surface_relations_for_run(run_id=run.id)
    merge_decisions = await repo.list_surface_merge_decisions_for_run(run_id=run.id)
    return {
        "surfaces": [
            _surface_payload(
                surface,
                ownership=ownership,
                reassignments=reassignments,
                relations=relations,
                merge_decisions=merge_decisions,
            )
            for surface in surfaces
        ]
    }


@router.get("/{document_id}/surface-relations")
async def list_document_surface_relations(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    repo = await _require_document_access(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    run = await _latest_surface_run(repo, project_id=project_id, document_id=document_id)
    if run is None:
        return {"relations": []}
    relations = await repo.list_surface_relations_for_run(run_id=run.id)
    return {"relations": [_relation_payload(item) for item in relations]}


@router.get("/{document_id}/surface-ownership")
async def list_document_surface_ownership(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    repo = await _require_document_access(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    run = await _latest_surface_run(repo, project_id=project_id, document_id=document_id)
    if run is None:
        return {"ownership": [], "reassignments": []}
    ownership = await repo.list_surface_ownership_for_run(run_id=run.id)
    reassignments = await repo.list_surface_reassignments_for_run(run_id=run.id)
    return {
        "ownership": [_ownership_payload(item) for item in ownership],
        "reassignments": [_reassignment_payload(item) for item in reassignments],
    }


@router.get("/{document_id}/surface-merge-decisions")
async def list_document_surface_merge_decisions(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: KnowledgeProjectAccessPort = Depends(get_project_repo),
    user_repo: PlatformUserAdminPort = Depends(get_user_repository),
):
    repo = await _require_document_access(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    run = await _latest_surface_run(repo, project_id=project_id, document_id=document_id)
    if run is None:
        return {"merge_decisions": []}
    merge_decisions = await repo.list_surface_merge_decisions_for_run(run_id=run.id)
    return {
        "merge_decisions": [
            _merge_decision_payload(item) for item in merge_decisions
        ]
    }


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
        compiler_run_id=surface.run_id,
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
