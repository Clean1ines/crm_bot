"""
Knowledge repository for RAG with hybrid search.

Clean Architecture contract:
- DB rows are converted to explicit typed read views inside this repository.
- Repository read methods do not return dict/Mapping compatibility objects.
"""

import json
from dataclasses import asdict
from datetime import datetime
from collections.abc import Mapping, Sequence
from typing import cast

import asyncpg

from src.application.errors import ConflictError, NotFoundError, ValidationError

from src.domain.project_plane.knowledge_views import (
    KnowledgeAnswerCandidateSummaryView,
    KnowledgeCompilerBatchView,
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
    KnowledgeSearchResultView,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerRun,
    RetrievalSurfaceCompilerStage,
    RetrievalSurfaceSourceChild,
    RetrievalSurfaceSourceUnit,
    RetrievalSurfaceDraft,
    RetrievalSurfaceRelation,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
    RetrievalSurfaceMergeDecision,
    SurfacePublicationStatus,
    SurfaceCompilerRunStatus,
    SurfaceSourceChildLabelKind,
    SurfaceStatus,
    SurfaceKind,
    SurfaceRelationType,
    SurfaceQuestionKind,
    SurfaceMergeDecisionType,
)
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.db.repositories.knowledge_answer_candidate_persistence import (
    delete_raw_answer_candidates_for_batch as persist_delete_raw_answer_candidates_for_batch,
    upsert_answer_candidates,
    upsert_candidate_clusters,
)
from src.infrastructure.db.repositories.knowledge_answer_candidate_queries import (
    get_document_answer_candidate_summary as query_document_answer_candidate_summary,
    list_document_raw_answer_candidates as query_document_raw_answer_candidates,
)
from src.infrastructure.db.repositories.knowledge_compiler_run_persistence import (
    complete_compiler_batch as persist_complete_compiler_batch,
    complete_compiler_run as persist_complete_compiler_run,
    fail_compiler_batch as persist_fail_compiler_batch,
    fail_compiler_run as persist_fail_compiler_run,
    mark_compiler_batch_processing as persist_mark_compiler_batch_processing,
    upsert_compiler_batch,
    upsert_compiler_run,
)
from src.infrastructure.db.repositories.knowledge_curation_entry_operations import (
    attach_question_to_entry as run_attach_question_to_entry,
    rebuild_entry_embedding as run_rebuild_entry_embedding,
    apply_manual_entry_merge as run_apply_manual_entry_merge,
    restore_entry_version as run_restore_entry_version,
    update_entry_content as run_update_entry_content,
    update_entry_status_visibility as run_update_entry_status_visibility,
)
from src.infrastructure.db.repositories.knowledge_search_ranking import (
    optional_row_text,
    optional_row_value,
    preview_score_and_trace,
    search_score_and_trace,
)
from src.infrastructure.db.repositories.knowledge_source_chunk_persistence import (
    delete_document_source_chunks,
    list_document_source_chunks as query_document_source_chunks,
    replace_document_source_chunks,
)
from src.infrastructure.db.repositories.knowledge_search_queries import (
    RUNTIME_HYBRID_SEARCH_SQL,
    RUNTIME_PREVIEW_SEARCH_SQL,
    RUNTIME_VECTOR_SEARCH_SQL,
)
from src.infrastructure.llm.embedding_service import embed_batch, embed_text
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid
from src.domain.project_plane.embedding_text import CANONICAL_EMBEDDING_TEXT_VERSION

from src.domain.project_plane.knowledge_curation import (
    KnowledgeCurationEntryView,
    KnowledgeEntryMergeApplyResult,
    KnowledgeEntryMergePreview,
    KnowledgeEntryMergeRequest,
    KnowledgeEntryPatch,
    KnowledgeEntryVersionView,
)
from src.domain.project_plane.knowledge_compilation import (
    CompilerRun,
    CompilationMetrics,
    CandidateCluster,
    AnswerCandidate,
    CompilerBatch,
    CanonicalKnowledgeEntry,
    EmbeddingText,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import (
    first_source_excerpt,
    json_list_from_db,
    json_object_from_db,
    jsonb_object_payload,
    normalize_timestamp,
    pg_vector_text,
    source_ref_views_from_payload,
    source_refs_from_db,
    text_tuple_from_json,
)
from src.infrastructure.db.repositories.knowledge_document_queries import (
    get_document_detail as query_document_detail,
    is_document_processing_cancelled as query_document_processing_cancelled,
    list_project_documents,
)
from src.infrastructure.db.repositories.knowledge_document_persistence import (
    create_document as persist_create_document,
    mark_document_processing_cancelled,
    merge_document_preprocessing_metrics,
    resume_document_processing as persist_resume_document_processing,
    update_document_preprocessing_status as persist_update_document_preprocessing_status,
    update_document_status as persist_update_document_status,
)
from src.infrastructure.db.repositories.knowledge_entry_persistence import (
    batched_canonical_entries,
    delete_document_retrieval_surface,
    delete_retrieval_surface,
    entry_embedding_text,
    entry_embedding_text_version,
    enrichment_payload,
    replace_entry_source_refs,
    sync_entry_retrieval_surface,
)
from src.infrastructure.db.repositories.knowledge_curation_action_persistence import (
    create_manual_curation_action,
    create_or_get_result_action,
    load_existing_manual_curation_action,
    mark_action_applied,
    mark_action_completed_with_result,
    mark_action_failed,
    mark_action_rejected,
)


logger = get_logger(__name__)

CANCELLABLE_KNOWLEDGE_JOB_TYPES = (
    "process_knowledge_upload",
    "run_full_rag_eval",
)
TERMINAL_QUEUE_STATUSES = (
    "completed",
    "failed",
    "cancelled",
    "succeeded",
    "done",
)
ANSWERABLE_KNOWLEDGE_ENTRY_KINDS = tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))


def _jsonb_array(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        value = []
    return json.dumps(list(value), ensure_ascii=False)


def _surface_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class KnowledgeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._usage_repo = ModelUsageRepository(pool)

    async def cancel_document_processing(
        self,
        *,
        project_id: str,
        document_id: str,
        reason: str,
    ) -> bool:
        document_uuid = ensure_uuid(document_id)
        document_id_text = str(document_id)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                document_updated = await mark_document_processing_cancelled(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    reason=reason,
                )
                if not document_updated:
                    return False

                await conn.execute(
                    """
                    UPDATE execution_queue
                    SET
                        status = 'failed',
                        attempts = max_attempts,
                        error = $4,
                        locked_at = NULL,
                        worker_id = NULL,
                        next_attempt_at = NULL,
                        updated_at = now()
                    WHERE payload->>'document_id' = $1
                      AND task_type = ANY($2::text[])
                      AND NOT (status = ANY($3::text[]))
                    """,
                    document_id_text,
                    list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
                    list(TERMINAL_QUEUE_STATUSES),
                    reason,
                )

                await conn.execute(
                    """
                    UPDATE knowledge_surface_compiler_runs
                    SET
                        status = 'cancelled',
                        error_type = 'processing_cancelled',
                        error_message = $2,
                        completed_at = now(),
                        updated_at = now()
                    WHERE document_id = $1
                      AND status NOT IN ('completed', 'failed', 'cancelled')
                    """,
                    document_uuid,
                    reason,
                )

                await conn.execute(
                    """
                    UPDATE knowledge_surface_compiler_stages
                    SET
                        status = 'cancelled',
                        error_type = 'processing_cancelled',
                        error_message = $2,
                        completed_at = now(),
                        updated_at = now()
                    WHERE document_id = $1
                      AND status NOT IN ('completed', 'failed', 'cancelled')
                    """,
                    document_uuid,
                    reason,
                )

                await conn.execute(
                    """
                    UPDATE knowledge_compiler_runs
                    SET
                        status = 'failed',
                        error = $2,
                        finished_at = now(),
                        updated_at = now()
                    WHERE document_id = $1
                      AND status NOT IN ('completed', 'failed', 'cancelled')
                    """,
                    document_uuid,
                    reason,
                )

        return True

    async def resume_document_processing(
        self,
        *,
        project_id: str,
        document_id: str,
        mode: KnowledgePreprocessingMode,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await persist_resume_document_processing(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    mode=mode,
                    model=model,
                    prompt_version=prompt_version,
                    metrics=metrics,
                )

    async def is_document_processing_cancelled(self, document_id: str) -> bool:
        async with self.pool.acquire() as conn:
            return await query_document_processing_cancelled(
                conn,
                document_id=document_id,
            )

    async def list_runtime_entry_titles(
        self,
        *,
        project_id: str,
        exclude_document_id: str | None = None,
        limit: int = 300,
    ) -> tuple[str, ...]:
        safe_limit = max(1, min(limit, 500))
        excluded_document_uuid = (
            ensure_uuid(exclude_document_id) if exclude_document_id else None
        )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT title
                FROM knowledge_retrieval_surface
                WHERE project_id = $1
                  AND status = 'published'
                  AND visibility = 'runtime'
                  AND ($2::uuid IS NULL OR document_id <> $2::uuid)
                  AND NULLIF(BTRIM(title), '') IS NOT NULL
                ORDER BY title ASC
                LIMIT $3
                """,
                ensure_uuid(project_id),
                excluded_document_uuid,
                safe_limit,
            )

        titles: list[str] = []
        for row in rows:
            title = str(row["title"] or "").strip()
            if title and title not in titles:
                titles.append(title)

        return tuple(titles)

    async def list_document_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[CanonicalKnowledgeEntry, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    ke.id,
                    ke.project_id,
                    ke.document_id,
                    ke.compiler_run_id,
                    ke.stable_key,
                    ke.entry_kind,
                    ke.title,
                    ke.answer,
                    ke.status,
                    ke.visibility,
                    ke.version,
                    ke.compiler_version,
                    COALESCE(ke.embedding_text, rs.embedding_text, '') AS embedding_text,
                    COALESCE(
                        ke.embedding_text_version,
                        rs.embedding_text_version,
                        ''
                    ) AS embedding_text_version,
                    ke.enrichment,
                    ke.metadata,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'source_index', sr.source_index,
                                'quote', sr.quote,
                                'source_chunk_id', sr.source_chunk_id,
                                'start_offset', sr.start_offset,
                                'end_offset', sr.end_offset,
                                'confidence', sr.confidence
                            )
                            ORDER BY sr.source_index, sr.quote
                        ) FILTER (WHERE sr.entry_id IS NOT NULL),
                        '[]'::jsonb
                    ) AS source_refs
                FROM knowledge_entries AS ke
                LEFT JOIN knowledge_retrieval_surface AS rs ON rs.entry_id = ke.id
                LEFT JOIN knowledge_entry_source_refs AS sr ON sr.entry_id = ke.id
                WHERE ke.project_id = $1
                  AND ke.document_id = $2
                  AND ke.status = 'published'
                  AND ke.visibility = 'runtime'
                GROUP BY
                    ke.id,
                    rs.embedding_text,
                    rs.embedding_text_version
                ORDER BY ke.created_at ASC, ke.id ASC
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )

        entries: list[CanonicalKnowledgeEntry] = []
        for row in rows:
            enrichment = json_object_from_db(row["enrichment"])
            embedding_text = str(row["embedding_text"] or "").strip()
            embedding_text_version = (
                str(row["embedding_text_version"] or "").strip()
                or CANONICAL_EMBEDDING_TEXT_VERSION
            )
            source_refs = source_refs_from_db(row["source_refs"])
            entries.append(
                CanonicalKnowledgeEntry(
                    id=str(row["id"]),
                    project_id=str(row["project_id"]),
                    document_id=str(row["document_id"]),
                    compiler_run_id=str(row["compiler_run_id"] or ""),
                    stable_key=str(row["stable_key"]),
                    entry_kind=KnowledgeEntryKind(str(row["entry_kind"])),
                    title=str(row["title"]),
                    answer=str(row["answer"]),
                    source_refs=source_refs,
                    enrichment=KnowledgeEnrichment(
                        questions=text_tuple_from_json(enrichment.get("questions")),
                        paraphrases=text_tuple_from_json(enrichment.get("paraphrases")),
                        synonyms=text_tuple_from_json(enrichment.get("synonyms")),
                        typo_queries=text_tuple_from_json(
                            enrichment.get("typo_queries")
                        ),
                        colloquial_queries=text_tuple_from_json(
                            enrichment.get("colloquial_queries")
                        ),
                        tags=text_tuple_from_json(enrichment.get("tags")),
                        retrieval_guards=text_tuple_from_json(
                            enrichment.get("retrieval_guards")
                        ),
                    ),
                    embedding_text=(
                        EmbeddingText(
                            value=embedding_text,
                            version=embedding_text_version,
                        )
                        if embedding_text
                        else None
                    ),
                    status=KnowledgeEntryStatus(str(row["status"])),
                    visibility=KnowledgeEntryVisibility(str(row["visibility"])),
                    version=int(row["version"]),
                    compiler_version=str(row["compiler_version"] or ""),
                    embedding_text_version=embedding_text_version,
                    metadata=json_object_from_db(row["metadata"]),
                )
            )

        return tuple(entries)

    async def apply_document_answer_resolution_retightening(
        self,
        *,
        project_id: str,
        document_id: str,
        updated_entries: Sequence[CanonicalKnowledgeEntry],
        archived_entry_ids: Sequence[str],
        metrics: JsonObject,
    ) -> JsonObject:
        embeddings: list[list[float]] = []
        if updated_entries:
            embedding_result = await embed_batch(
                [entry_embedding_text(entry) for entry in updated_entries]
            )
            embeddings = embedding_result.embeddings
            if embedding_result.usage is not None:
                await self._usage_repo.record_event(
                    ModelUsageEventCreate.from_measurement(
                        project_id=project_id,
                        source="knowledge_upload",
                        measurement=embedding_result.usage,
                        document_id=document_id,
                    )
                )

        if len(embeddings) != len(updated_entries):
            raise RuntimeError("embedding provider returned invalid vector count")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for archived_entry_id in archived_entry_ids:
                    entry_uuid = ensure_uuid(archived_entry_id)
                    await delete_retrieval_surface(conn, entry_id=str(entry_uuid))
                    await conn.execute(
                        """
                        UPDATE knowledge_entries
                        SET status = 'archived',
                            visibility = 'hidden',
                            metadata = COALESCE(metadata, '{}'::jsonb) || $4::jsonb,
                            updated_at = now()
                        WHERE id = $1
                          AND project_id = $2
                          AND document_id = $3
                        """,
                        entry_uuid,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id),
                        jsonb_object_payload(
                            {
                                "answer_resolution_archived": True,
                                "answer_resolution_reason": (
                                    "merged_into_survivor_entry"
                                ),
                            }
                        ),
                    )

                for index, entry in enumerate(updated_entries):
                    entry_uuid = ensure_uuid(entry.id)
                    enrichment_payload_value = enrichment_payload(entry)
                    embedding_text = entry_embedding_text(entry)
                    embedding_text_version = entry_embedding_text_version(entry)
                    metadata = dict(entry.metadata)
                    metadata["answer_resolution_metrics"] = dict(metrics)

                    await conn.execute(
                        """
                        UPDATE knowledge_entries
                        SET title = $4,
                            answer = $5,
                            status = $6,
                            visibility = $7,
                            version = $8,
                            compiler_version = $9,
                            embedding_text = $10,
                            embedding_text_version = $11,
                            enrichment = $12::jsonb,
                            metadata = $13::jsonb,
                            updated_at = now()
                        WHERE id = $1
                          AND project_id = $2
                          AND document_id = $3
                        """,
                        entry_uuid,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id),
                        entry.title,
                        entry.answer,
                        entry.status.value,
                        entry.visibility.value,
                        entry.version,
                        entry.compiler_version,
                        embedding_text,
                        embedding_text_version,
                        jsonb_object_payload(enrichment_payload_value),
                        jsonb_object_payload(metadata),
                    )

                    source_refs_payload = await replace_entry_source_refs(
                        conn,
                        entry_id=entry.id,
                        source_refs=entry.source_refs,
                    )

                    await sync_entry_retrieval_surface(
                        conn,
                        project_id=project_id,
                        document_id=document_id,
                        entry=entry,
                        embedding=embeddings[index],
                        enrichment_payload_value=enrichment_payload_value,
                        source_refs_payload_value=source_refs_payload,
                        metadata=metadata,
                        status=entry.status.value,
                        visibility=entry.visibility.value,
                    )

                await merge_document_preprocessing_metrics(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    metrics={"answer_resolution": dict(metrics)},
                )

        result: JsonObject = dict(metrics)
        result["status"] = "completed"
        result["updated_entry_count"] = len(updated_entries)
        result["archived_entry_count"] = len(archived_entry_ids)
        return result

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        if limit <= 0:
            return []

        query_embedding_result = await embed_text(query)
        query_embedding_str = pg_vector_text(query_embedding_result.embedding)
        project_uuid = ensure_uuid(project_id)

        if query_embedding_result.usage is not None:
            await self._usage_repo.record_event(
                ModelUsageEventCreate.from_measurement(
                    project_id=project_id,
                    source="rag_search",
                    measurement=query_embedding_result.usage,
                    thread_id=thread_id,
                )
            )

        candidate_limit = max(limit * 10, 50)

        async with self.pool.acquire() as conn:
            if not hybrid_fallback:
                rows = await conn.fetch(
                    RUNTIME_VECTOR_SEARCH_SQL,
                    query_embedding_str,
                    project_uuid,
                    limit,
                    list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
                )
            else:
                rows = await conn.fetch(
                    RUNTIME_HYBRID_SEARCH_SQL,
                    query_embedding_str,
                    query,
                    project_uuid,
                    candidate_limit,
                    candidate_limit,
                    list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
                )

        results: list[KnowledgeSearchResultView] = []

        for row in rows:
            content = str(row["content"])
            score_trace = search_score_and_trace(row, query=query, content=content)
            source_refs = source_ref_views_from_payload(
                optional_row_value(row, "source_refs")
            )
            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=content,
                    score=score_trace.score,
                    method=score_trace.method,
                    document_id=optional_row_text(row, "document_id"),
                    source=optional_row_text(row, "source"),
                    document_status=optional_row_text(row, "document_status"),
                    entry_kind=optional_row_text(row, "entry_kind"),
                    title=optional_row_text(row, "title"),
                    source_excerpt=first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    embedding_text=optional_row_text(row, "embedding_text"),
                    questions=optional_row_value(row, "questions"),
                    synonyms=optional_row_value(row, "synonyms"),
                    tags=optional_row_value(row, "tags"),
                    trace=score_trace.trace,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]:
        if limit <= 0:
            return []

        normalized_query = query.strip()
        if not normalized_query:
            return []

        candidate_limit = max(limit * 12, 50)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                RUNTIME_PREVIEW_SEARCH_SQL,
                normalized_query,
                ensure_uuid(project_id),
                candidate_limit,
                list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
            )

        results: list[KnowledgeSearchResultView] = []
        for row in rows:
            content = str(row["content"])
            score_trace = preview_score_and_trace(
                row,
                query=normalized_query,
                content=content,
            )
            source_refs = source_ref_views_from_payload(
                optional_row_value(row, "source_refs")
            )
            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=content,
                    score=score_trace.score,
                    method="retrieval_surface_lexical",
                    document_id=optional_row_text(row, "document_id"),
                    source=optional_row_text(row, "source"),
                    document_status=optional_row_text(row, "document_status"),
                    entry_kind=optional_row_text(row, "entry_kind"),
                    title=optional_row_text(row, "title"),
                    source_excerpt=first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    embedding_text=optional_row_text(row, "embedding_text"),
                    questions=optional_row_value(row, "questions"),
                    synonyms=optional_row_value(row, "synonyms"),
                    tags=optional_row_value(row, "tags"),
                    trace=score_trace.trace,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def create_compiler_run(self, run: CompilerRun) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await upsert_compiler_run(conn, run=run)

    async def create_surface_compiler_run(
        self,
        run: RetrievalSurfaceCompilerRun,
    ) -> RetrievalSurfaceCompilerRun:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO knowledge_surface_compiler_runs (
                    id, project_id, document_id, mode, status, compiler_kind, model,
                    prompt_version, started_at, completed_at, error_type,
                    error_message, metrics
                )
                VALUES (
                    $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13::jsonb
                )
                """,
                ensure_uuid(run.id),
                ensure_uuid(run.project_id),
                ensure_uuid(run.document_id),
                run.mode,
                run.status,
                run.compiler_kind,
                run.model,
                run.prompt_version,
                run.started_at,
                run.completed_at,
                run.error_type,
                run.error_message,
                json.dumps(run.metrics, ensure_ascii=False),
            )
        return run

    async def update_surface_compiler_run_status(
        self,
        *,
        run_id: str,
        status: SurfaceCompilerRunStatus,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_surface_compiler_runs
                SET
                    status = $2,
                    error_type = $3,
                    error_message = $4,
                    completed_at = CASE WHEN $2 IN ('completed', 'failed', 'cancelled') THEN now() ELSE NULL END,
                    updated_at = now()
                WHERE id = $1::uuid
                """,
                ensure_uuid(run_id),
                status,
                error_type,
                error_message,
            )

    async def get_latest_surface_run_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> RetrievalSurfaceCompilerRun | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, project_id, document_id, mode, status, compiler_kind, model,
                       prompt_version, started_at, completed_at, error_type,
                       error_message, metrics
                FROM knowledge_surface_compiler_runs
                WHERE project_id = $1::uuid AND document_id = $2::uuid
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )
        if row is None:
            return None
        return RetrievalSurfaceCompilerRun(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            mode=cast(KnowledgePreprocessingMode, str(row["mode"])),
            status=cast(SurfaceCompilerRunStatus, str(row["status"])),
            compiler_kind=str(row["compiler_kind"]),
            model=str(row["model"]),
            prompt_version=str(row["prompt_version"]),
            started_at=_surface_timestamp(row["started_at"]),
            completed_at=_surface_timestamp(row["completed_at"]),
            error_type=str(row["error_type"])
            if row["error_type"] is not None
            else None,
            error_message=str(row["error_message"])
            if row["error_message"] is not None
            else None,
            metrics=json_object_from_db(row["metrics"]),
        )

    async def list_surface_runs_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[RetrievalSurfaceCompilerRun, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, project_id, document_id, mode, status, compiler_kind, model,
                       prompt_version, started_at, completed_at, error_type,
                       error_message, metrics
                FROM knowledge_surface_compiler_runs
                WHERE project_id = $1::uuid AND document_id = $2::uuid
                ORDER BY created_at DESC, id DESC
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )
        return tuple(
            RetrievalSurfaceCompilerRun(
                id=str(row["id"]),
                project_id=str(row["project_id"]),
                document_id=str(row["document_id"]),
                mode=cast(KnowledgePreprocessingMode, str(row["mode"])),
                status=cast(SurfaceCompilerRunStatus, str(row["status"])),
                compiler_kind=str(row["compiler_kind"]),
                model=str(row["model"]),
                prompt_version=str(row["prompt_version"]),
                started_at=_surface_timestamp(row["started_at"]),
                completed_at=_surface_timestamp(row["completed_at"]),
                error_type=str(row["error_type"])
                if row["error_type"] is not None
                else None,
                error_message=str(row["error_message"])
                if row["error_message"] is not None
                else None,
                metrics=json_object_from_db(row["metrics"]),
            )
            for row in rows
        )

    async def list_surface_stages_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceCompilerStage, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, stage_kind, status, model,
                       prompt_version, input_summary, output_summary, tokens_input,
                       tokens_output, tokens_total, error_type, error_message,
                       metrics, started_at, completed_at
                FROM knowledge_surface_compiler_stages
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        return tuple(
            RetrievalSurfaceCompilerStage(
                id=str(row["id"]),
                run_id=str(row["run_id"]),
                document_id=str(row["document_id"]),
                stage_kind=str(row["stage_kind"]),
                status=cast(SurfaceCompilerRunStatus, str(row["status"])),
                model=str(row["model"]),
                prompt_version=str(row["prompt_version"]),
                input_summary=str(row["input_summary"]),
                output_summary=str(row["output_summary"]),
                tokens_input=int(row["tokens_input"]),
                tokens_output=int(row["tokens_output"]),
                tokens_total=int(row["tokens_total"]),
                error_type=str(row["error_type"])
                if row["error_type"] is not None
                else None,
                error_message=str(row["error_message"])
                if row["error_message"] is not None
                else None,
                started_at=_surface_timestamp(row["started_at"]),
                completed_at=_surface_timestamp(row["completed_at"]),
                metrics=json_object_from_db(row["metrics"]),
            )
            for row in rows
        )

    async def save_surface_source_units(
        self,
        *,
        run_id: str,
        document_id: str,
        source_units: tuple[RetrievalSurfaceSourceUnit, ...],
    ) -> None:
        if not source_units:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for unit in source_units:
                    children_payload = [
                        {
                            "title": child.title,
                            "body": child.body,
                            "raw_text": child.raw_text,
                            "label_kind": child.label_kind,
                            "metadata": child.metadata,
                        }
                        for child in unit.children
                    ]
                    await conn.execute(
                        """
                        INSERT INTO knowledge_surface_source_units (
                            id, run_id, document_id, source_unit_key, source_chunk_indexes,
                            title, body, children, raw_text, section_path, source_refs,
                            preprocessing_mode, metadata
                        ) VALUES (
                            $1::uuid, $2::uuid, $3::uuid, $4, $5::int[],
                            $6, $7, $8::jsonb, $9, $10::text[], $11::jsonb,
                            $12, $13::jsonb
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        ensure_uuid(unit.id),
                        ensure_uuid(run_id),
                        ensure_uuid(document_id),
                        unit.source_unit_key,
                        list(unit.source_chunk_indexes),
                        unit.title,
                        unit.body,
                        json.dumps(children_payload, ensure_ascii=False),
                        unit.raw_text,
                        list(unit.section_path),
                        json.dumps(list(unit.source_refs), ensure_ascii=False),
                        unit.preprocessing_mode,
                        json.dumps(unit.metadata, ensure_ascii=False),
                    )

    async def list_surface_source_units_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceSourceUnit, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, source_unit_key, source_chunk_indexes,
                       title, body, children, raw_text, section_path, source_refs,
                       preprocessing_mode, metadata
                FROM knowledge_surface_source_units
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        result: list[RetrievalSurfaceSourceUnit] = []
        for row in rows:
            children_payload = json_list_from_db(row["children"])
            children = tuple(
                RetrievalSurfaceSourceChild(
                    title=str(item.get("title", "")),
                    body=str(item.get("body", "")),
                    raw_text=str(item.get("raw_text", "")),
                    label_kind=cast(
                        SurfaceSourceChildLabelKind,
                        str(item.get("label_kind", "other")),
                    ),
                    metadata=json_object_from_unknown(item.get("metadata", {})),
                )
                for item in children_payload
                if isinstance(item, dict)
            )
            source_refs_payload = json_list_from_db(row["source_refs"])
            source_refs = tuple(str(item) for item in source_refs_payload)
            section_path = tuple(str(item) for item in (row["section_path"] or []))
            chunk_indexes = tuple(
                int(item) for item in (row["source_chunk_indexes"] or [])
            )
            result.append(
                RetrievalSurfaceSourceUnit(
                    id=str(row["id"]),
                    run_id=str(row["run_id"]),
                    document_id=str(row["document_id"]),
                    source_unit_key=str(row["source_unit_key"]),
                    source_chunk_indexes=chunk_indexes,
                    title=str(row["title"]),
                    body=str(row["body"]),
                    children=children,
                    raw_text=str(row["raw_text"]),
                    section_path=section_path,
                    source_refs=source_refs,
                    preprocessing_mode=cast(
                        KnowledgePreprocessingMode, str(row["preprocessing_mode"])
                    ),
                    metadata=json_object_from_db(row["metadata"]),
                )
            )
        return tuple(result)

    async def save_surfaces(
        self,
        *,
        run_id: str,
        document_id: str,
        surfaces: tuple[RetrievalSurfaceDraft, ...],
    ) -> None:
        if not surfaces:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for surface in surfaces:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_surfaces (
                            id, run_id, document_id, local_surface_key, title,
                            canonical_question, surface_kind, answer_scope,
                            question_scope, exclusion_scope, answer, short_answer,
                            status, publication_status, source_refs, source_excerpt,
                            confidence, warnings, metadata, source_chunk_indexes,
                            linked_candidate_id, linked_canonical_entry_id,
                            linked_runtime_entry_id
                        ) VALUES (
                            $1::uuid, $2::uuid, $3::uuid, $4, $5,
                            $6, $7, $8,
                            $9, $10, $11, $12,
                            $13, $14, $15::jsonb, $16,
                            $17, $18::jsonb, $19::jsonb, $20::int[],
                            $21::uuid, $22::uuid,
                            $23::uuid
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        ensure_uuid(surface.id),
                        ensure_uuid(run_id),
                        ensure_uuid(document_id),
                        surface.local_surface_key,
                        surface.title,
                        surface.canonical_question,
                        surface.surface_kind,
                        surface.answer_scope,
                        surface.question_scope,
                        surface.exclusion_scope,
                        surface.answer,
                        surface.short_answer,
                        surface.status,
                        surface.publication_status,
                        json.dumps(list(surface.source_refs), ensure_ascii=False),
                        surface.source_excerpt,
                        surface.confidence,
                        json.dumps(list(surface.warnings), ensure_ascii=False),
                        json.dumps(surface.metadata, ensure_ascii=False),
                        list(surface.source_chunk_indexes),
                        ensure_uuid(surface.linked_candidate_id)
                        if surface.linked_candidate_id
                        else None,
                        ensure_uuid(surface.linked_canonical_entry_id)
                        if surface.linked_canonical_entry_id
                        else None,
                        ensure_uuid(surface.linked_runtime_entry_id)
                        if surface.linked_runtime_entry_id
                        else None,
                    )

    async def list_surfaces_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceDraft, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, local_surface_key, title,
                       canonical_question, surface_kind, answer_scope,
                       question_scope, exclusion_scope, answer, short_answer,
                       status, publication_status, source_refs, source_excerpt,
                       confidence, warnings, metadata, source_chunk_indexes,
                       linked_candidate_id, linked_canonical_entry_id,
                       linked_runtime_entry_id
                FROM knowledge_surfaces
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        result: list[RetrievalSurfaceDraft] = []
        for row in rows:
            result.append(
                RetrievalSurfaceDraft(
                    id=str(row["id"]),
                    run_id=str(row["run_id"]),
                    document_id=str(row["document_id"]),
                    local_surface_key=str(row["local_surface_key"]),
                    title=str(row["title"]),
                    canonical_question=str(row["canonical_question"]),
                    surface_kind=cast(SurfaceKind, str(row["surface_kind"])),
                    answer_scope=str(row["answer_scope"]),
                    question_scope=str(row["question_scope"]),
                    exclusion_scope=str(row["exclusion_scope"]),
                    answer=str(row["answer"]),
                    short_answer=str(row["short_answer"]),
                    status=cast(SurfaceStatus, str(row["status"])),
                    publication_status=cast(
                        SurfacePublicationStatus, str(row["publication_status"])
                    ),
                    source_refs=tuple(
                        str(item) for item in json_list_from_db(row["source_refs"])
                    ),
                    source_excerpt=str(row["source_excerpt"]),
                    confidence=float(row["confidence"]),
                    warnings=tuple(
                        str(item) for item in json_list_from_db(row["warnings"])
                    ),
                    metadata=json_object_from_db(row["metadata"]),
                    source_chunk_indexes=tuple(
                        int(item) for item in (row["source_chunk_indexes"] or [])
                    ),
                    linked_candidate_id=str(row["linked_candidate_id"])
                    if row["linked_candidate_id"] is not None
                    else None,
                    linked_canonical_entry_id=str(row["linked_canonical_entry_id"])
                    if row["linked_canonical_entry_id"] is not None
                    else None,
                    linked_runtime_entry_id=str(row["linked_runtime_entry_id"])
                    if row["linked_runtime_entry_id"] is not None
                    else None,
                )
            )
        return tuple(result)

    async def get_surface_by_id(
        self,
        *,
        surface_id: str,
    ) -> RetrievalSurfaceDraft | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, run_id, document_id, local_surface_key, title,
                       canonical_question, surface_kind, answer_scope,
                       question_scope, exclusion_scope, answer, short_answer,
                       status, publication_status, source_refs, source_excerpt,
                       confidence, warnings, metadata, source_chunk_indexes,
                       linked_candidate_id, linked_canonical_entry_id,
                       linked_runtime_entry_id
                FROM knowledge_surfaces
                WHERE id = $1::uuid
                """,
                ensure_uuid(surface_id),
            )
        if row is None:
            return None
        return RetrievalSurfaceDraft(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            document_id=str(row["document_id"]),
            local_surface_key=str(row["local_surface_key"]),
            title=str(row["title"]),
            canonical_question=str(row["canonical_question"]),
            surface_kind=cast(SurfaceKind, str(row["surface_kind"])),
            answer_scope=str(row["answer_scope"]),
            question_scope=str(row["question_scope"]),
            exclusion_scope=str(row["exclusion_scope"]),
            answer=str(row["answer"]),
            short_answer=str(row["short_answer"]),
            status=cast(SurfaceStatus, str(row["status"])),
            publication_status=cast(
                SurfacePublicationStatus, str(row["publication_status"])
            ),
            source_refs=tuple(
                str(item) for item in json_list_from_db(row["source_refs"])
            ),
            source_excerpt=str(row["source_excerpt"]),
            confidence=float(row["confidence"]),
            warnings=tuple(str(item) for item in json_list_from_db(row["warnings"])),
            metadata=json_object_from_db(row["metadata"]),
            source_chunk_indexes=tuple(
                int(item) for item in (row["source_chunk_indexes"] or [])
            ),
            linked_candidate_id=str(row["linked_candidate_id"])
            if row["linked_candidate_id"] is not None
            else None,
            linked_canonical_entry_id=str(row["linked_canonical_entry_id"])
            if row["linked_canonical_entry_id"] is not None
            else None,
            linked_runtime_entry_id=str(row["linked_runtime_entry_id"])
            if row["linked_runtime_entry_id"] is not None
            else None,
        )

    async def update_surface_publication_status(
        self,
        *,
        surface_id: str,
        publication_status: SurfacePublicationStatus,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_surfaces
                SET publication_status = $2::text,
                    updated_at = now()
                WHERE id = $1::uuid
                """,
                ensure_uuid(surface_id),
                publication_status,
            )

    async def link_surface_to_runtime_entry(
        self,
        *,
        surface_id: str,
        runtime_entry_id: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_surfaces
                SET linked_runtime_entry_id = $2::uuid,
                    updated_at = now()
                WHERE id = $1::uuid
                """,
                ensure_uuid(surface_id),
                ensure_uuid(runtime_entry_id),
            )

    async def save_surface_relations(
        self,
        *,
        run_id: str,
        document_id: str,
        relations: tuple[RetrievalSurfaceRelation, ...],
    ) -> None:
        if not relations:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for rel in relations:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_surface_relations (
                            id, run_id, document_id, parent_surface_key,
                            child_surface_key, relation_type, reason,
                            confidence, source_refs
                        ) VALUES (
                            $1::uuid, $2::uuid, $3::uuid, $4,
                            $5, $6, $7,
                            $8, $9::jsonb
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        ensure_uuid(rel.id),
                        ensure_uuid(run_id),
                        ensure_uuid(document_id),
                        rel.parent_surface_key,
                        rel.child_surface_key,
                        rel.relation_type,
                        rel.reason,
                        rel.confidence,
                        json.dumps(list(rel.source_refs), ensure_ascii=False),
                    )

    async def list_surface_relations_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceRelation, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, parent_surface_key,
                       child_surface_key, relation_type, reason,
                       confidence, source_refs
                FROM knowledge_surface_relations
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        return tuple(
            RetrievalSurfaceRelation(
                id=str(row["id"]),
                run_id=str(row["run_id"]),
                document_id=str(row["document_id"]),
                parent_surface_key=str(row["parent_surface_key"]),
                child_surface_key=str(row["child_surface_key"]),
                relation_type=cast(SurfaceRelationType, str(row["relation_type"])),
                reason=str(row["reason"]),
                confidence=float(row["confidence"]),
                source_refs=tuple(
                    str(item) for item in json_list_from_db(row["source_refs"])
                ),
            )
            for row in rows
        )

    async def save_surface_question_ownership(
        self,
        *,
        run_id: str,
        document_id: str,
        ownership: tuple[SurfaceQuestionOwnership, ...],
    ) -> None:
        if not ownership:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item in ownership:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_surface_question_ownership (
                            id, run_id, document_id, question, owner_surface_key,
                            question_kind, confidence, reason,
                            rejected_from_surface_keys
                        ) VALUES (
                            $1::uuid, $2::uuid, $3::uuid, $4, $5,
                            $6, $7, $8,
                            $9::jsonb
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        ensure_uuid(item.id),
                        ensure_uuid(run_id),
                        ensure_uuid(document_id),
                        item.question,
                        item.owner_surface_key,
                        item.question_kind,
                        item.confidence,
                        item.reason,
                        json.dumps(
                            list(item.rejected_from_surface_keys), ensure_ascii=False
                        ),
                    )

    async def list_surface_ownership_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[SurfaceQuestionOwnership, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, question, owner_surface_key,
                       question_kind, confidence, reason,
                       rejected_from_surface_keys
                FROM knowledge_surface_question_ownership
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        return tuple(
            SurfaceQuestionOwnership(
                id=str(row["id"]),
                run_id=str(row["run_id"]),
                document_id=str(row["document_id"]),
                question=str(row["question"]),
                owner_surface_key=str(row["owner_surface_key"]),
                question_kind=cast(SurfaceQuestionKind, str(row["question_kind"])),
                confidence=float(row["confidence"]),
                reason=str(row["reason"]),
                rejected_from_surface_keys=tuple(
                    str(i) for i in json_list_from_db(row["rejected_from_surface_keys"])
                ),
            )
            for row in rows
        )

    async def save_surface_question_reassignments(
        self,
        *,
        run_id: str,
        document_id: str,
        reassignments: tuple[SurfaceQuestionReassignment, ...],
    ) -> None:
        if not reassignments:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item in reassignments:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_surface_question_reassignments (
                            id, run_id, document_id, question,
                            from_surface_key, to_surface_key, reason, confidence
                        ) VALUES (
                            $1::uuid, $2::uuid, $3::uuid, $4,
                            $5, $6, $7, $8
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        ensure_uuid(item.id),
                        ensure_uuid(run_id),
                        ensure_uuid(document_id),
                        item.question,
                        item.from_surface_key,
                        item.to_surface_key,
                        item.reason,
                        item.confidence,
                    )

    async def list_surface_reassignments_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[SurfaceQuestionReassignment, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, question,
                       from_surface_key, to_surface_key, reason, confidence
                FROM knowledge_surface_question_reassignments
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        return tuple(
            SurfaceQuestionReassignment(
                id=str(row["id"]),
                run_id=str(row["run_id"]),
                document_id=str(row["document_id"]),
                question=str(row["question"]),
                from_surface_key=str(row["from_surface_key"]),
                to_surface_key=str(row["to_surface_key"]),
                reason=str(row["reason"]),
                confidence=float(row["confidence"]),
            )
            for row in rows
        )

    async def save_surface_merge_decisions(
        self,
        *,
        run_id: str,
        document_id: str,
        merge_decisions: tuple[RetrievalSurfaceMergeDecision, ...],
    ) -> None:
        if not merge_decisions:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item in merge_decisions:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_surface_merge_decisions (
                            id, run_id, document_id, survivor_surface_key,
                            merged_surface_keys, keep_separate_surface_keys,
                            decision_type, reason, confidence
                        ) VALUES (
                            $1::uuid, $2::uuid, $3::uuid, $4,
                            $5::jsonb, $6::jsonb,
                            $7, $8, $9
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        ensure_uuid(item.id),
                        ensure_uuid(run_id),
                        ensure_uuid(document_id),
                        item.survivor_surface_key,
                        json.dumps(list(item.merged_surface_keys), ensure_ascii=False),
                        json.dumps(
                            list(item.keep_separate_surface_keys), ensure_ascii=False
                        ),
                        item.decision_type,
                        item.reason,
                        item.confidence,
                    )

    async def list_surface_merge_decisions_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceMergeDecision, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, document_id, survivor_surface_key,
                       merged_surface_keys, keep_separate_surface_keys,
                       decision_type, reason, confidence
                FROM knowledge_surface_merge_decisions
                WHERE run_id = $1::uuid
                ORDER BY created_at ASC, id ASC
                """,
                ensure_uuid(run_id),
            )
        return tuple(
            RetrievalSurfaceMergeDecision(
                id=str(row["id"]),
                run_id=str(row["run_id"]),
                document_id=str(row["document_id"]),
                survivor_surface_key=str(row["survivor_surface_key"]),
                merged_surface_keys=tuple(
                    str(i) for i in json_list_from_db(row["merged_surface_keys"])
                ),
                keep_separate_surface_keys=tuple(
                    str(i) for i in json_list_from_db(row["keep_separate_surface_keys"])
                ),
                decision_type=cast(SurfaceMergeDecisionType, str(row["decision_type"])),
                reason=str(row["reason"]),
                confidence=float(row["confidence"]),
            )
            for row in rows
        )

    async def list_surface_relations_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[RetrievalSurfaceRelation, ...]:
        latest = await self.get_latest_surface_run_for_document(
            project_id=project_id,
            document_id=document_id,
        )
        if latest is None:
            return ()
        return await self.list_surface_relations_for_run(run_id=latest.id)

    async def list_surface_ownership_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[SurfaceQuestionOwnership, ...]:
        latest = await self.get_latest_surface_run_for_document(
            project_id=project_id,
            document_id=document_id,
        )
        if latest is None:
            return ()
        return await self.list_surface_ownership_for_run(run_id=latest.id)

    async def list_surface_reassignments_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[SurfaceQuestionReassignment, ...]:
        latest = await self.get_latest_surface_run_for_document(
            project_id=project_id,
            document_id=document_id,
        )
        if latest is None:
            return ()
        return await self.list_surface_reassignments_for_run(run_id=latest.id)

    async def create_surface_compiler_stage(
        self,
        stage: RetrievalSurfaceCompilerStage,
    ) -> RetrievalSurfaceCompilerStage:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO knowledge_surface_compiler_stages (
                    id, run_id, document_id, stage_kind, status, model,
                    prompt_version, input_summary, output_summary, tokens_input,
                    tokens_output, tokens_total, error_type, error_message,
                    metrics, started_at, completed_at
                )
                VALUES (
                    $1::uuid, $2::uuid, $3::uuid, $4, $5, $6,
                    $7, $8, $9, $10,
                    $11, $12, $13, $14,
                    $15::jsonb, $16, $17
                )
                """,
                ensure_uuid(stage.id),
                ensure_uuid(stage.run_id),
                ensure_uuid(stage.document_id),
                stage.stage_kind,
                stage.status,
                stage.model,
                stage.prompt_version,
                stage.input_summary,
                stage.output_summary,
                stage.tokens_input,
                stage.tokens_output,
                stage.tokens_total,
                stage.error_type,
                stage.error_message,
                json.dumps(stage.metrics, ensure_ascii=False),
                stage.started_at,
                stage.completed_at,
            )
        return stage

    async def create_compiler_batches(
        self,
        *,
        project_id: str,
        document_id: str,
        batches: Sequence[CompilerBatch],
    ) -> int:
        if not batches:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for batch in batches:
                    await upsert_compiler_batch(
                        conn,
                        project_id=project_id,
                        document_id=document_id,
                        batch=batch,
                    )

        return len(batches)

    async def mark_compiler_batch_processing(
        self,
        batch_id: str,
        *,
        attempt_count: int,
    ) -> None:
        async with self.pool.acquire() as conn:
            await persist_mark_compiler_batch_processing(
                conn,
                batch_id,
                attempt_count=attempt_count,
            )

    async def complete_compiler_batch(
        self,
        batch_id: str,
        *,
        model: str,
        prompt_version: str,
        tokens_input: int,
        tokens_output: int,
        tokens_total: int,
    ) -> None:
        async with self.pool.acquire() as conn:
            await persist_complete_compiler_batch(
                conn,
                batch_id,
                model=model,
                prompt_version=prompt_version,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tokens_total=tokens_total,
            )

    async def fail_compiler_batch(
        self,
        batch_id: str,
        *,
        error_type: str,
        error_message: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await persist_fail_compiler_batch(
                conn,
                batch_id,
                error_type=error_type,
                error_message=error_message,
            )

    async def complete_compiler_run(
        self,
        compiler_run_id: str,
        metrics: CompilationMetrics,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await persist_complete_compiler_run(
                    conn,
                    compiler_run_id,
                    metrics=metrics,
                )

    async def fail_compiler_run(
        self,
        compiler_run_id: str,
        error: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await persist_fail_compiler_run(conn, compiler_run_id, error=error)

    async def delete_raw_answer_candidates_for_batch(
        self,
        *,
        project_id: str,
        document_id: str,
        batch_id: str,
    ) -> int:
        async with self.pool.acquire() as conn:
            return await persist_delete_raw_answer_candidates_for_batch(
                conn,
                project_id=project_id,
                document_id=document_id,
                batch_id=batch_id,
            )

    async def add_answer_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
        candidates: Sequence[AnswerCandidate],
    ) -> int:
        if not candidates:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await upsert_answer_candidates(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    candidates=candidates,
                )

    async def add_candidate_clusters(
        self,
        *,
        project_id: str,
        document_id: str,
        clusters: Sequence[CandidateCluster],
    ) -> int:
        if not clusters:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await upsert_candidate_clusters(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    clusters=clusters,
                )

    async def add_canonical_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        entries: Sequence[CanonicalKnowledgeEntry],
    ) -> int:
        """Persist canonical entries, source refs, and runtime retrieval surface atomically."""
        if not entries:
            return 0

        for batch in batched_canonical_entries(
            entries, settings.KNOWLEDGE_EMBED_BATCH_SIZE
        ):
            texts = [entry_embedding_text(entry) for entry in batch]
            embedding_result = await embed_batch(texts)
            embeddings = embedding_result.embeddings

            if embedding_result.usage is not None:
                await self._usage_repo.record_event(
                    ModelUsageEventCreate.from_measurement(
                        project_id=project_id,
                        source="knowledge_upload",
                        measurement=embedding_result.usage,
                        document_id=document_id,
                    )
                )

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for index, entry in enumerate(batch):
                        entry_uuid = ensure_uuid(entry.id)
                        enrichment_payload_value = enrichment_payload(entry)
                        embedding_text = entry_embedding_text(entry)
                        embedding_text_version = entry_embedding_text_version(entry)

                        await conn.execute(
                            """
                            INSERT INTO knowledge_entries (
                                id,
                                project_id,
                                document_id,
                                compiler_run_id,
                                stable_key,
                                entry_kind,
                                title,
                                answer,
                                status,
                                visibility,
                                version,
                                compiler_version,
                                embedding_text,
                                embedding_text_version,
                                enrichment,
                                metadata
                            )
                            VALUES (
                                $1,
                                $2,
                                $3,
                                $4,
                                $5,
                                $6,
                                $7,
                                $8,
                                $9,
                                $10,
                                $11,
                                $12,
                                $13,
                                $14,
                                $15::jsonb,
                                $16::jsonb
                            )
                            ON CONFLICT (project_id, document_id, stable_key, version)
                            DO UPDATE SET
                                entry_kind = EXCLUDED.entry_kind,
                                title = EXCLUDED.title,
                                answer = EXCLUDED.answer,
                                status = EXCLUDED.status,
                                visibility = EXCLUDED.visibility,
                                compiler_version = EXCLUDED.compiler_version,
                                embedding_text = EXCLUDED.embedding_text,
                                embedding_text_version = EXCLUDED.embedding_text_version,
                                enrichment = EXCLUDED.enrichment,
                                metadata = EXCLUDED.metadata,
                                updated_at = now()
                            """,
                            entry_uuid,
                            ensure_uuid(project_id),
                            ensure_uuid(document_id),
                            entry.compiler_run_id or None,
                            entry.stable_key,
                            entry.entry_kind.value,
                            entry.title,
                            entry.answer,
                            entry.status.value,
                            entry.visibility.value,
                            entry.version,
                            entry.compiler_version,
                            embedding_text,
                            embedding_text_version,
                            jsonb_object_payload(enrichment_payload_value),
                            jsonb_object_payload(entry.metadata),
                        )

                        source_refs_payload = await replace_entry_source_refs(
                            conn,
                            entry_id=entry.id,
                            source_refs=entry.source_refs,
                        )

                        await sync_entry_retrieval_surface(
                            conn,
                            project_id=project_id,
                            document_id=document_id,
                            entry=entry,
                            embedding=embeddings[index],
                            enrichment_payload_value=enrichment_payload_value,
                            source_refs_payload_value=source_refs_payload,
                            metadata=entry.metadata,
                            status=entry.status.value,
                            visibility=entry.visibility.value,
                        )

        return len(entries)

    async def list_document_source_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[SourceChunk, ...]:
        async with self.pool.acquire() as conn:
            return await query_document_source_chunks(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

    async def add_source_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: Sequence[SourceChunk],
    ) -> int:
        """Persist raw extracted SourceChunk records separately from runtime KB rows."""
        if not chunks:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                return await replace_document_source_chunks(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    chunks=chunks,
                )

    async def create_document(
        self,
        project_id: str,
        file_name: str,
        file_size: int | None = None,
        uploaded_by: str | None = None,
    ) -> str:
        logger.info(
            "Creating knowledge document",
            extra={"project_id": project_id, "file_name": file_name},
        )

        async with self.pool.acquire() as conn:
            document_id = await persist_create_document(
                conn,
                project_id=project_id,
                file_name=file_name,
                file_size=file_size,
                uploaded_by=uploaded_by,
            )

        logger.info("Document created", extra={"document_id": document_id})
        return document_id

    async def get_documents(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[KnowledgeDocumentView]:
        logger.debug(
            "Fetching knowledge documents",
            extra={"project_id": project_id, "limit": limit, "offset": offset},
        )

        async with self.pool.acquire() as conn:
            documents = await list_project_documents(
                conn,
                project_id=project_id,
                limit=limit,
                offset=offset,
            )

        logger.debug("Retrieved knowledge documents", extra={"count": len(documents)})
        return documents

    async def get_document(
        self, document_id: str
    ) -> KnowledgeDocumentDetailView | None:
        logger.debug("Fetching knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            return await query_document_detail(conn, document_id=document_id)

    async def list_document_compiler_batches(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[KnowledgeCompilerBatchView, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    compiler_run_id,
                    batch_index,
                    batch_count,
                    status,
                    source_chunk_ids,
                    source_chunk_indexes,
                    attempt_count,
                    model,
                    prompt_version,
                    tokens_input,
                    tokens_output,
                    tokens_total,
                    error_type,
                    error_message,
                    started_at,
                    finished_at,
                    updated_at
                FROM knowledge_compiler_batches
                WHERE project_id = $1
                  AND document_id = $2
                ORDER BY compiler_run_id, batch_index
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )

        return tuple(
            KnowledgeCompilerBatchView(
                id=str(row["id"]),
                compiler_run_id=str(row["compiler_run_id"]),
                batch_index=int(row["batch_index"] or 0),
                batch_count=int(row["batch_count"] or 0),
                status=str(row["status"]),
                source_chunk_ids=row["source_chunk_ids"],
                source_chunk_indexes=row["source_chunk_indexes"],
                attempt_count=int(row["attempt_count"] or 0),
                model=str(row["model"] or ""),
                prompt_version=str(row["prompt_version"] or ""),
                tokens_input=int(row["tokens_input"] or 0),
                tokens_output=int(row["tokens_output"] or 0),
                tokens_total=int(row["tokens_total"] or 0),
                error_type=str(row["error_type"] or ""),
                error_message=str(row["error_message"] or ""),
                started_at=normalize_timestamp(row["started_at"]),
                finished_at=normalize_timestamp(row["finished_at"]),
                updated_at=normalize_timestamp(row["updated_at"]),
            )
            for row in rows
        )

    async def list_document_raw_answer_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[AnswerCandidate, ...]:
        async with self.pool.acquire() as conn:
            return await query_document_raw_answer_candidates(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

    async def get_document_answer_candidate_summary(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeAnswerCandidateSummaryView:
        async with self.pool.acquire() as conn:
            return await query_document_answer_candidate_summary(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        logger.info(
            "Updating document status",
            extra={"document_id": document_id, "status": status},
        )

        async with self.pool.acquire() as conn:
            await persist_update_document_status(
                conn,
                document_id=document_id,
                status=status,
                error=error,
            )

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: KnowledgePreprocessingMode,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await persist_update_document_preprocessing_status(
                conn,
                document_id=document_id,
                mode=mode,
                status=status,
                error=error,
                model=model,
                prompt_version=prompt_version,
                metrics=metrics,
            )

    async def _cancel_document_jobs(
        self,
        conn: asyncpg.Connection,
        document_id: str,
    ) -> None:
        await conn.execute(
            """
            UPDATE execution_queue
            SET status = 'cancelled',
                error = COALESCE(
                    error,
                    'Cancelled because source knowledge document was deleted'
                ),
                updated_at = NOW()
            WHERE task_type = ANY($1::text[])
              AND COALESCE(status, '') <> ALL($2::text[])
              AND payload::jsonb ->> 'document_id' = $3
            """,
            list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
            list(TERMINAL_QUEUE_STATUSES),
            document_id,
        )

    async def _cancel_project_knowledge_jobs(
        self,
        conn: asyncpg.Connection,
        project_id: str,
    ) -> None:
        await conn.execute(
            """
            UPDATE execution_queue
            SET status = 'cancelled',
                error = COALESCE(
                    error,
                    'Cancelled because project knowledge base was cleared'
                ),
                updated_at = NOW()
            WHERE task_type = ANY($1::text[])
              AND COALESCE(status, '') <> ALL($2::text[])
              AND payload::jsonb ->> 'project_id' = $3
            """,
            list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
            list(TERMINAL_QUEUE_STATUSES),
            project_id,
        )

    async def create_or_get_knowledge_edit_action(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        source_result_id: str,
        source_run_id: str,
        source_question_id: str,
        action_index: int,
        actor_user_id: str,
        action_type: str,
        target_entry_id: str | None,
        reason: str,
        payload: JsonObject,
    ) -> JsonObject:
        async with self.pool.acquire() as conn:
            return await create_or_get_result_action(
                conn,
                action_id=action_id,
                project_id=project_id,
                document_id=document_id,
                source_result_id=source_result_id,
                source_run_id=source_run_id,
                source_question_id=source_question_id,
                action_index=action_index,
                actor_user_id=actor_user_id,
                action_type=action_type,
                target_entry_id=target_entry_id,
                reason=reason,
                payload=payload,
            )

    async def mark_knowledge_edit_action_applied(
        self,
        action_id: str,
        *,
        result_payload: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await mark_action_applied(
                conn,
                action_id,
                result_payload=result_payload,
            )

    async def mark_knowledge_edit_action_rejected(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await mark_action_rejected(
                conn,
                action_id,
                error=error,
                result_payload=result_payload,
            )

    async def mark_knowledge_edit_action_failed(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await mark_action_failed(
                conn,
                action_id,
                error=error,
                result_payload=result_payload,
            )

    async def attach_question_to_entry(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
        question: str,
        reason: str,
        actor_user_id: str,
    ) -> None:
        await run_attach_question_to_entry(
            self.pool,
            action_id=action_id,
            project_id=project_id,
            document_id=document_id,
            target_entry_id=target_entry_id,
            question=question,
            reason=reason,
            actor_user_id=actor_user_id,
        )

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None:
        await run_rebuild_entry_embedding(
            self.pool,
            self._usage_repo,
            action_id=action_id,
            project_id=project_id,
            document_id=document_id,
            target_entry_id=target_entry_id,
        )

    async def delete_document_chunks(self, document_id: str) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await delete_document_retrieval_surface(
                    conn,
                    document_id=document_id,
                )
                await conn.execute(
                    "DELETE FROM knowledge_entries WHERE document_id = $1",
                    ensure_uuid(document_id),
                )
                await conn.execute(
                    "DELETE FROM knowledge_compiler_runs WHERE document_id = $1",
                    ensure_uuid(document_id),
                )
                await delete_document_source_chunks(
                    conn,
                    document_id=document_id,
                )

    async def delete_document(self, document_id: str) -> None:
        logger.info("Deleting knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            await self._cancel_document_jobs(conn, document_id)
            await conn.execute(
                "DELETE FROM knowledge_documents WHERE id = $1",
                ensure_uuid(document_id),
            )

        logger.info("Document deleted", extra={"document_id": document_id})

    async def get_document_for_curation(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    kd.id,
                    kd.project_id,
                    kd.file_name,
                    kd.status,
                    kd.preprocessing_status,
                    kd.preprocessing_metrics,
                    kd.created_at,
                    kd.updated_at,
                    COALESCE((
                        SELECT count(*)
                        FROM knowledge_entries AS ke
                        WHERE ke.project_id = kd.project_id
                          AND ke.document_id = kd.id
                    ), 0) AS canonical_entry_count,
                    COALESCE((
                        SELECT count(*)
                        FROM knowledge_retrieval_surface AS rs
                        WHERE rs.project_id = kd.project_id
                          AND rs.document_id = kd.id
                    ), 0) AS retrieval_surface_count,
                    0 AS legacy_chunk_count
                FROM knowledge_documents AS kd
                WHERE kd.project_id = $1 AND kd.id = $2
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )
        if row is None:
            return None

        metrics = json_object_from_db(row["preprocessing_metrics"])
        metrics_stage = metrics.get("stage")
        preprocessing_status = str(row["preprocessing_status"] or "")
        document_status = str(row["status"] or "")
        processing_stage = (
            str(metrics_stage)
            if metrics_stage
            else preprocessing_status or document_status
        )

        canonical_entry_count = int(row["canonical_entry_count"] or 0)
        legacy_chunk_count = int(row["legacy_chunk_count"] or 0)

        return {
            "id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "file_name": str(row["file_name"] or ""),
            "status": document_status,
            "processing_stage": processing_stage,
            "preprocessing_status": preprocessing_status,
            "preprocessing_metrics": metrics,
            "canonical_entry_count": canonical_entry_count,
            "retrieval_surface_count": int(row["retrieval_surface_count"] or 0),
            "legacy_chunk_count": legacy_chunk_count,
            # Backward-compatible UI field. It is derived, not a physical column.
            "chunk_count": canonical_entry_count or legacy_chunk_count,
            "created_at": normalize_timestamp(row["created_at"]),
            "updated_at": normalize_timestamp(row["updated_at"]),
        }

    def _curation_entry_from_row(
        self, row: asyncpg.Record
    ) -> KnowledgeCurationEntryView:
        enrichment = json_object_from_db(row["enrichment"])
        metadata = json_object_from_db(row["metadata"])
        source_refs = tuple(
            item
            for item in json_list_from_db(row["source_refs"])
            if isinstance(item, Mapping)
        )
        status = KnowledgeEntryStatus(str(row["status"]))
        visibility = KnowledgeEntryVisibility(str(row["visibility"]))
        runtime_eligible = (
            status == KnowledgeEntryStatus.PUBLISHED
            and visibility == KnowledgeEntryVisibility.RUNTIME
            and bool(source_refs)
        )
        return KnowledgeCurationEntryView(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            stable_key=str(row["stable_key"]),
            entry_kind=KnowledgeEntryKind(str(row["entry_kind"])),
            title=str(row["title"]),
            answer=str(row["answer"]),
            status=status,
            visibility=visibility,
            version=int(row["version"]),
            enrichment=enrichment,
            source_refs=source_refs,
            metadata=metadata,
            has_retrieval_surface=bool(row["has_retrieval_surface"]),
            has_embedding=bool(row["has_embedding"]),
            runtime_eligible=runtime_eligible,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list_document_canonical_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[KnowledgeCurationEntryView, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    ke.id,
                    ke.project_id,
                    ke.document_id,
                    ke.stable_key,
                    ke.entry_kind,
                    ke.title,
                    ke.answer,
                    ke.status,
                    ke.visibility,
                    ke.version,
                    ke.enrichment,
                    ke.metadata,
                    ke.created_at,
                    ke.updated_at,
                    (rs.entry_id IS NOT NULL) AS has_retrieval_surface,
                    (NULLIF(BTRIM(COALESCE(ke.embedding_text, rs.embedding_text, '')), '') IS NOT NULL
                        OR rs.embedding IS NOT NULL) AS has_embedding,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'source_index', sr.source_index,
                                'quote', sr.quote,
                                'source_chunk_id', sr.source_chunk_id,
                                'start_offset', sr.start_offset,
                                'end_offset', sr.end_offset,
                                'confidence', sr.confidence,
                                'key', concat_ws(':', sr.source_chunk_id, sr.source_index, sr.quote_hash)
                            )
                            ORDER BY sr.source_index, sr.quote
                        ) FILTER (WHERE sr.entry_id IS NOT NULL),
                        '[]'::jsonb
                    ) AS source_refs
                FROM knowledge_entries AS ke
                LEFT JOIN knowledge_retrieval_surface AS rs ON rs.entry_id = ke.id
                LEFT JOIN knowledge_entry_source_refs AS sr ON sr.entry_id = ke.id
                WHERE ke.project_id = $1
                  AND ke.document_id = $2
                GROUP BY ke.id, rs.entry_id, rs.embedding, rs.embedding_text
                ORDER BY ke.updated_at DESC, ke.created_at DESC, ke.id ASC
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )
        return tuple(self._curation_entry_from_row(row) for row in rows)

    async def load_entry_for_curation(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
    ) -> KnowledgeCurationEntryView | None:
        entries = await self.list_document_canonical_entries(
            project_id=project_id, document_id=document_id
        )
        for entry in entries:
            if entry.id == entry_id:
                return entry
        return None

    async def _create_manual_curation_action(
        self,
        conn: asyncpg.Connection,
        *,
        project_id: str,
        document_id: str,
        action_type: str,
        actor_user_id: str,
        target_entry_id: str | None,
        target_entry_ids: Sequence[str],
        reason: str,
        payload: Mapping[str, object],
        idempotency_key: str,
        source_kind: str,
    ) -> str:
        return await create_manual_curation_action(
            conn,
            project_id=project_id,
            document_id=document_id,
            action_type=action_type,
            actor_user_id=actor_user_id,
            target_entry_id=target_entry_id,
            target_entry_ids=target_entry_ids,
            reason=reason,
            payload=payload,
            idempotency_key=idempotency_key,
            source_kind=source_kind,
        )

    def _manual_merge_action_payload(
        self, *, request: KnowledgeEntryMergeRequest
    ) -> Mapping[str, object]:
        return {
            "request": json_object_from_unknown(asdict(request)),
        }

    async def _load_existing_manual_curation_action(
        self,
        conn: asyncpg.Connection,
        *,
        project_id: str,
        document_id: str,
        source_kind: str,
        idempotency_key: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object] | None:
        return await load_existing_manual_curation_action(
            conn,
            project_id=project_id,
            document_id=document_id,
            source_kind=source_kind,
            idempotency_key=idempotency_key,
            payload=payload,
        )

    def _merge_apply_result_from_payload(
        self,
        *,
        action_id: str,
        payload: Mapping[str, object],
        preview: KnowledgeEntryMergePreview,
    ) -> KnowledgeEntryMergeApplyResult:
        absorbed_raw = payload.get("absorbed_entry_ids")
        absorbed_entry_ids = (
            tuple(str(item) for item in absorbed_raw)
            if isinstance(absorbed_raw, Sequence)
            and not isinstance(absorbed_raw, str | bytes | bytearray)
            else ()
        )
        parent_version_raw = payload.get("parent_version")
        if isinstance(parent_version_raw, int):
            parent_version = parent_version_raw
        elif isinstance(parent_version_raw, str):
            try:
                parent_version = int(parent_version_raw)
            except ValueError:
                parent_version = 0
        else:
            parent_version = 0

        return KnowledgeEntryMergeApplyResult(
            ok=bool(payload.get("ok")),
            partial=bool(payload.get("partial")),
            action_id=str(payload.get("action_id") or action_id),
            parent_entry_id=str(payload.get("parent_entry_id") or ""),
            absorbed_entry_ids=absorbed_entry_ids,
            parent_version=parent_version,
            embedding_rebuilt=bool(payload.get("embedding_rebuilt")),
            rerun_eval_enqueued=bool(payload.get("rerun_eval_enqueued")),
            error=str(payload.get("error") or ""),
            preview=preview,
            replayed=True,
        )

    async def _fetch_entry_row_for_update(
        self,
        conn: asyncpg.Connection,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
    ) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """
            SELECT id, project_id, document_id, compiler_run_id, stable_key, entry_kind,
                   title, answer, status, visibility, version, compiler_version,
                   embedding_text, embedding_text_version, enrichment, metadata
            FROM knowledge_entries
            WHERE id = $1 AND project_id = $2 AND document_id = $3
            FOR UPDATE
            """,
            ensure_uuid(entry_id),
            ensure_uuid(project_id),
            ensure_uuid(document_id),
        )

    async def update_entry_status_visibility(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        action_type: str,
        actor_user_id: str,
        expected_version: int | None,
        status: str,
        visibility: str,
        reason: str,
        idempotency_key: str,
        rebuild_embedding: bool = False,
    ) -> KnowledgeCurationEntryView:
        result = await run_update_entry_status_visibility(
            self.pool,
            create_action=self._create_manual_curation_action,
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            action_type=action_type,
            actor_user_id=actor_user_id,
            expected_version=expected_version,
            status=status,
            visibility=visibility,
            reason=reason,
            idempotency_key=idempotency_key,
        )

        if (
            status == KnowledgeEntryStatus.PUBLISHED.value
            and visibility == KnowledgeEntryVisibility.RUNTIME.value
        ):
            await self.rebuild_entry_embedding(
                action_id=result.action_id,
                project_id=project_id,
                document_id=document_id,
                target_entry_id=entry_id,
            )

        loaded = await self.load_entry_for_curation(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
        )
        if loaded is None:
            raise NotFoundError("knowledge entry not found")
        return loaded

    async def update_entry_content(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        patch: KnowledgeEntryPatch,
    ) -> KnowledgeCurationEntryView:
        result = await run_update_entry_content(
            self.pool,
            create_action=self._create_manual_curation_action,
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            actor_user_id=actor_user_id,
            patch=patch,
        )

        if patch.rebuild_embedding:
            await self.rebuild_entry_embedding(
                action_id=result.action_id,
                project_id=project_id,
                document_id=document_id,
                target_entry_id=entry_id,
            )

        loaded = await self.load_entry_for_curation(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
        )
        if loaded is None:
            raise NotFoundError("knowledge entry not found")
        return loaded

    async def apply_manual_entry_merge(
        self,
        *,
        project_id: str,
        document_id: str,
        actor_user_id: str,
        request: KnowledgeEntryMergeRequest,
        preview: KnowledgeEntryMergePreview,
    ) -> KnowledgeEntryMergeApplyResult:
        merge_action_payload = self._manual_merge_action_payload(request=request)
        mutation_result = await run_apply_manual_entry_merge(
            self.pool,
            create_action=self._create_manual_curation_action,
            load_existing_action=self._load_existing_manual_curation_action,
            project_id=project_id,
            document_id=document_id,
            actor_user_id=actor_user_id,
            request=request,
            preview=preview,
            merge_action_payload=merge_action_payload,
        )

        if mutation_result.replay_payload is not None:
            return self._merge_apply_result_from_payload(
                action_id=mutation_result.action_id,
                payload=mutation_result.replay_payload,
                preview=preview,
            )

        embedding_rebuilt = False
        partial = False
        error = ""
        if request.rebuild_embedding:
            try:
                await self.rebuild_entry_embedding(
                    action_id=mutation_result.action_id,
                    project_id=project_id,
                    document_id=document_id,
                    target_entry_id=request.parent_entry_id,
                )
                embedding_rebuilt = True
            except Exception as exc:
                partial = True
                error = f"embedding_rebuild_failed:{type(exc).__name__}"

        result = KnowledgeEntryMergeApplyResult(
            ok=not partial,
            partial=partial,
            action_id=mutation_result.action_id,
            parent_entry_id=request.parent_entry_id,
            absorbed_entry_ids=request.absorbed_entry_ids,
            parent_version=mutation_result.parent_version,
            embedding_rebuilt=embedding_rebuilt,
            rerun_eval_enqueued=False,
            error=error,
            preview=preview,
            replayed=False,
        )
        merge_result_payload: dict[str, object] = {
            "ok": result.ok,
            "partial": result.partial,
            "action_id": result.action_id,
            "parent_entry_id": result.parent_entry_id,
            "absorbed_entry_ids": list(result.absorbed_entry_ids),
            "parent_version": result.parent_version,
            "embedding_rebuilt": result.embedding_rebuilt,
            "rerun_eval_enqueued": result.rerun_eval_enqueued,
            "error": result.error,
            "replayed": False,
        }
        async with self.pool.acquire() as conn:
            await mark_action_completed_with_result(
                conn,
                mutation_result.action_id,
                status="applied_with_warning" if partial else "applied",
                error=error,
                result_payload=merge_result_payload,
            )
        return result

    async def create_manual_rebuild_embedding_action(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        expected_version: int | None,
        reason: str,
        idempotency_key: str,
    ) -> str:
        if not idempotency_key.strip():
            raise ValidationError("idempotency_key is required")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                before = await self._fetch_entry_row_for_update(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    entry_id=entry_id,
                )
                if before is None:
                    raise NotFoundError("knowledge entry not found")
                if (
                    expected_version is not None
                    and int(before["version"]) != expected_version
                ):
                    raise ConflictError("version_conflict")

                return await self._create_manual_curation_action(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    action_type="rebuild_embedding",
                    actor_user_id=actor_user_id,
                    target_entry_id=entry_id,
                    target_entry_ids=(entry_id,),
                    reason=reason,
                    payload={
                        "entry_id": entry_id,
                        "expected_version": expected_version,
                        "reason": reason,
                    },
                    idempotency_key=idempotency_key,
                    source_kind="manual_embedding_rebuild",
                )

    async def list_knowledge_curation_actions(
        self,
        *,
        project_id: str,
        document_id: str,
        limit: int,
    ) -> tuple[Mapping[str, object], ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, action_type, status, actor_user_id, target_entry_id, target_entry_ids_json,
                       reason, payload, result_payload, error, source_kind, idempotency_key,
                       created_at, applied_at, updated_at
                FROM knowledge_edit_actions
                WHERE project_id = $1 AND document_id = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
                max(1, min(limit, 200)),
            )
        return tuple(
            {
                "id": str(row["id"]),
                "action_type": str(row["action_type"]),
                "status": str(row["status"]),
                "actor_user_id": str(row["actor_user_id"] or ""),
                "target_entry_id": str(row["target_entry_id"] or ""),
                "target_entry_ids": json_list_from_db(row["target_entry_ids_json"]),
                "reason": str(row["reason"] or ""),
                "payload": json_object_from_db(row["payload"]),
                "result_payload": json_object_from_db(row["result_payload"]),
                "error": str(row["error"] or ""),
                "source_kind": str(row["source_kind"] or ""),
                "idempotency_key": str(row["idempotency_key"] or ""),
                "created_at": normalize_timestamp(row["created_at"]),
                "applied_at": normalize_timestamp(row["applied_at"]),
                "updated_at": normalize_timestamp(row["updated_at"]),
            }
            for row in rows
        )

    async def list_entry_versions(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
    ) -> tuple[KnowledgeEntryVersionView, ...]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, entry_id, project_id, document_id, action_id, from_version, to_version,
                       previous_snapshot, new_snapshot, created_at
                FROM knowledge_entry_versions
                WHERE project_id = $1 AND document_id = $2 AND entry_id = $3
                ORDER BY created_at DESC
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
                ensure_uuid(entry_id),
            )
        return tuple(
            KnowledgeEntryVersionView(
                id=str(row["id"]),
                entry_id=str(row["entry_id"]),
                project_id=str(row["project_id"]),
                document_id=str(row["document_id"]) if row["document_id"] else None,
                action_id=str(row["action_id"] or ""),
                from_version=int(row["from_version"]),
                to_version=int(row["to_version"]),
                previous_snapshot=json_object_from_db(row["previous_snapshot"]),
                new_snapshot=json_object_from_db(row["new_snapshot"]),
                created_at=row["created_at"],
            )
            for row in rows
        )

    async def restore_entry_version(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        version_id: str,
        actor_user_id: str,
        reason: str,
    ) -> KnowledgeCurationEntryView:
        await run_restore_entry_version(
            self.pool,
            create_action=self._create_manual_curation_action,
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            version_id=version_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )

        loaded = await self.load_entry_for_curation(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
        )
        if loaded is None:
            raise NotFoundError("knowledge entry not found")
        return loaded

    async def clear_project_knowledge(self, project_id: str) -> None:
        logger.info("Clearing project knowledge", extra={"project_id": project_id})

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._cancel_project_knowledge_jobs(conn, project_id)
                await conn.execute(
                    "DELETE FROM knowledge_documents WHERE project_id = $1",
                    ensure_uuid(project_id),
                )

        logger.info("Project knowledge cleared", extra={"project_id": project_id})
