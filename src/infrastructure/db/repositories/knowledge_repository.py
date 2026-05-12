"""
Knowledge repository for RAG with hybrid search.

Clean Architecture contract:
- DB rows are converted to explicit typed read views inside this repository.
- Repository read methods do not return dict/Mapping compatibility objects.
"""

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Protocol

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
    KnowledgeSearchResultView,
    SourceRefView,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.llm.embedding_service import embed_batch, embed_text
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid
from src.domain.project_plane.embedding_text import (
    build_canonical_entry_embedding_text,
    build_retrieval_surface_search_text,
)
from src.domain.project_plane.knowledge_compilation import (
    CompilerRun,
    CompilationMetrics,
    CandidateCluster,
    AnswerCandidate,
    CanonicalKnowledgeEntry,
    SourceChunk,
    SourceRef,
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


class _RowLookup(Protocol):
    def __getitem__(self, key: str) -> object: ...


def _optional_row_text(row: _RowLookup, key: str) -> str | None:
    try:
        value = row[key]
    except KeyError:
        return None

    return str(value) if value is not None else None


def _optional_row_value(row: _RowLookup, key: str) -> object:
    try:
        return row[key]
    except KeyError:
        return None


def _normalize_timestamp(value: object) -> str | None:
    """
    Keep test strings unchanged and serialize real datetime-like values only
    when the repository owns the DB-row normalization boundary.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _jsonb_array(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        value = []
    return json.dumps(list(value), ensure_ascii=False)


def _jsonb_object(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def _pg_vector_text(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _batched_canonical_entries(
    entries: Sequence[CanonicalKnowledgeEntry], batch_size: int
) -> Iterator[Sequence[CanonicalKnowledgeEntry]]:
    for start in range(0, len(entries), batch_size):
        yield entries[start : start + batch_size]


def _entry_embedding_text(entry: CanonicalKnowledgeEntry) -> str:
    return build_canonical_entry_embedding_text(entry).value


def _entry_embedding_text_version(entry: CanonicalKnowledgeEntry) -> str:
    return build_canonical_entry_embedding_text(entry).version


def _enrichment_payload(entry: CanonicalKnowledgeEntry) -> dict[str, object]:
    return {
        "questions": list(entry.enrichment.questions),
        "paraphrases": list(entry.enrichment.paraphrases),
        "synonyms": list(entry.enrichment.synonyms),
        "typo_queries": list(entry.enrichment.typo_queries),
        "colloquial_queries": list(entry.enrichment.colloquial_queries),
        "tags": list(entry.enrichment.tags),
        "retrieval_guards": list(entry.enrichment.retrieval_guards),
    }


def _source_ref_payload(ref: SourceRef) -> dict[str, object]:
    payload: dict[str, object] = {"quote": ref.quote}
    if ref.source_index is not None:
        payload["source_index"] = ref.source_index
    if ref.source_chunk_id is not None:
        payload["source_chunk_id"] = ref.source_chunk_id
    if ref.start_offset is not None:
        payload["start_offset"] = ref.start_offset
    if ref.end_offset is not None:
        payload["end_offset"] = ref.end_offset
    if ref.confidence is not None:
        payload["confidence"] = ref.confidence
    return payload


def _source_refs_payload(entry: CanonicalKnowledgeEntry) -> list[dict[str, object]]:
    return [_source_ref_payload(ref) for ref in entry.source_refs]


def _surface_search_text(entry: CanonicalKnowledgeEntry) -> str:
    return build_retrieval_surface_search_text(entry)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _source_ref_view_from_mapping(payload: Mapping[str, object]) -> SourceRefView:
    quote = " ".join(str(payload.get("quote") or "").strip().split())
    source_chunk_id_value = payload.get("source_chunk_id")
    return SourceRefView(
        source_index=_optional_int(payload.get("source_index")),
        quote=quote,
        source_chunk_id=str(source_chunk_id_value) if source_chunk_id_value else None,
        start_offset=_optional_int(payload.get("start_offset")),
        end_offset=_optional_int(payload.get("end_offset")),
        confidence=_optional_float(payload.get("confidence")),
    )


def _source_ref_views_from_payload(value: object) -> tuple[SourceRefView, ...]:
    if not isinstance(value, list):
        return ()

    refs: list[SourceRefView] = []
    for item in value:
        if isinstance(item, Mapping):
            ref = _source_ref_view_from_mapping(item)
            if ref.quote:
                refs.append(ref)
    return tuple(refs)


def _first_source_excerpt(source_refs: tuple[SourceRefView, ...]) -> str | None:
    for source_ref in source_refs:
        if source_ref.quote:
            return source_ref.quote
    return None


def _stage_e_metrics_payload(metrics: CompilationMetrics) -> dict[str, object]:
    return {
        "source_chunk_count": metrics.source_chunk_count,
        "answer_candidate_count": metrics.answer_candidate_count,
        "grounded_candidate_count": metrics.grounded_candidate_count,
        "rejected_candidate_count": metrics.rejected_candidate_count,
        "candidate_cluster_count": metrics.candidate_cluster_count,
        "canonical_entry_count": metrics.canonical_entry_count,
        "enriched_entry_count": metrics.enriched_entry_count,
        "embedded_entry_count": metrics.embedded_entry_count,
        "published_entry_count": metrics.published_entry_count,
        "fallback_row_count": metrics.fallback_row_count,
        "dropped_forbidden_count": metrics.dropped_forbidden_count,
        "entries_without_source_refs_count": metrics.entries_without_source_refs_count,
    }


def _stage_e_jsonb_array(values: Sequence[Mapping[str, object]]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _stage_e_candidate_source_refs_payload(
    candidate: AnswerCandidate,
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for source_ref in candidate.source_refs:
        payload.append(
            {
                "source_index": source_ref.source_index,
                "quote": source_ref.quote,
                "source_chunk_id": source_ref.source_chunk_id,
                "start_offset": source_ref.start_offset,
                "end_offset": source_ref.end_offset,
                "confidence": source_ref.confidence,
            }
        )
    return payload


class KnowledgeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._usage_repo = ModelUsageRepository(pool)

    def _query_tokens(self, text: str) -> set[str]:
        """
        Lightweight lexical normalization for hybrid ranking.

        This is intentionally deterministic and domain-agnostic:
        - works without LLM;
        - handles punctuation better than str.split();
        - keeps Russian and English words;
        - ignores very short noise tokens.
        """
        return {
            token
            for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())
            if len(token) >= 3
        }

    def _keyword_overlap(self, query: str, text: str) -> float:
        q = self._query_tokens(query)
        t = self._query_tokens(text)
        if not q:
            return 0.0
        return len(q & t) / len(q)

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
        query_embedding_str = _pg_vector_text(query_embedding_result.embedding)
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
                    """
                    SELECT
                        rs.entry_id AS id,
                        rs.answer AS content,
                        rs.document_id,
                        d.file_name AS source,
                        d.status AS document_status,
                        rs.entry_kind,
                        rs.title,
                        rs.source_refs,
                        rs.embedding_text,
                        rs.enrichment->'questions' AS questions,
                        rs.enrichment->'synonyms' AS synonyms,
                        rs.enrichment->'tags' AS tags,
                        rs.search_text,
                        (1 - (rs.embedding <=> $1::vector)) AS vector_score,
                        0.0::double precision AS lexical_score,
                        0.0::double precision AS exact_score
                    FROM knowledge_retrieval_surface AS rs
                    LEFT JOIN knowledge_documents AS d ON d.id = rs.document_id
                    WHERE rs.project_id = $2
                      AND rs.embedding IS NOT NULL
                      AND rs.entry_kind = ANY($4::text[])
                      AND rs.status = 'published'
                      AND rs.visibility = 'runtime'
                      AND (d.status = 'processed' OR d.status IS NULL)
                    ORDER BY rs.embedding <=> $1::vector
                    LIMIT $3
                    """,
                    query_embedding_str,
                    project_uuid,
                    limit,
                    list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
                )
            else:
                rows = await conn.fetch(
                    """
                    WITH q AS (
                        SELECT
                            $1::vector AS query_embedding,
                            websearch_to_tsquery('russian', $2) AS query_ts,
                            lower($2) AS query_text
                    ),
                    base AS (
                        SELECT
                            rs.entry_id AS id,
                            rs.answer AS content,
                            rs.document_id,
                            d.file_name AS source,
                            d.status AS document_status,
                            rs.entry_kind,
                            rs.title,
                            rs.source_refs,
                            rs.embedding_text,
                            rs.enrichment->'questions' AS questions,
                            rs.enrichment->'synonyms' AS synonyms,
                            rs.enrichment->'tags' AS tags,
                            rs.search_text,
                            rs.embedding
                        FROM knowledge_retrieval_surface AS rs
                        LEFT JOIN knowledge_documents AS d ON d.id = rs.document_id
                        WHERE rs.project_id = $3
                          AND rs.embedding IS NOT NULL
                          AND rs.entry_kind = ANY($6::text[])
                          AND rs.status = 'published'
                          AND rs.visibility = 'runtime'
                          AND (d.status = 'processed' OR d.status IS NULL)
                    ),
                    vector_candidates AS (
                        SELECT
                            base.*,
                            (1 - (base.embedding <=> q.query_embedding)) AS vector_score,
                            row_number() OVER (ORDER BY base.embedding <=> q.query_embedding) AS vector_rank
                        FROM base, q
                        ORDER BY base.embedding <=> q.query_embedding
                        LIMIT $4
                    ),
                    lexical_candidates AS (
                        SELECT
                            base.*,
                            ts_rank_cd(
                                to_tsvector('russian', COALESCE(base.search_text, '')),
                                q.query_ts
                            ) AS lexical_score,
                            row_number() OVER (
                                ORDER BY ts_rank_cd(
                                    to_tsvector('russian', COALESCE(base.search_text, '')),
                                    q.query_ts
                                ) DESC
                            ) AS lexical_rank
                        FROM base, q
                        WHERE to_tsvector('russian', COALESCE(base.search_text, '')) @@ q.query_ts
                        ORDER BY lexical_score DESC
                        LIMIT $4
                    ),
                    candidates AS (
                        SELECT
                            id,
                            content,
                            document_id,
                            source,
                            document_status,
                            entry_kind,
                            title,
                            source_refs,
                            embedding_text,
                            questions,
                            synonyms,
                            tags,
                            search_text,
                            vector_score,
                            0.0::double precision AS lexical_score,
                            vector_rank,
                            NULL::bigint AS lexical_rank
                        FROM vector_candidates

                        UNION ALL

                        SELECT
                            id,
                            content,
                            document_id,
                            source,
                            document_status,
                            entry_kind,
                            title,
                            source_refs,
                            embedding_text,
                            questions,
                            synonyms,
                            tags,
                            search_text,
                            0.0::double precision AS vector_score,
                            lexical_score,
                            NULL::bigint AS vector_rank,
                            lexical_rank
                        FROM lexical_candidates
                    ),
                    merged AS (
                        SELECT
                            id,
                            max(content) AS content,
                            max(document_id::text)::uuid AS document_id,
                            max(source) AS source,
                            max(document_status) AS document_status,
                            max(entry_kind) AS entry_kind,
                            max(title) AS title,
                            (jsonb_agg(source_refs)->0) AS source_refs,
                            max(embedding_text) AS embedding_text,
                            (jsonb_agg(questions)->0) AS questions,
                            (jsonb_agg(synonyms)->0) AS synonyms,
                            (jsonb_agg(tags)->0) AS tags,
                            max(search_text) AS search_text,
                            max(vector_score) AS vector_score,
                            max(lexical_score) AS lexical_score,
                            min(vector_rank) AS vector_rank,
                            min(lexical_rank) AS lexical_rank
                        FROM candidates
                        GROUP BY id
                    )
                    SELECT
                        id,
                        content,
                        document_id,
                        source,
                        document_status,
                        entry_kind,
                        title,
                        source_refs,
                        embedding_text,
                        questions,
                        synonyms,
                        tags,
                        search_text,
                        vector_score,
                        lexical_score,
                        CASE
                            WHEN lower(search_text) LIKE ('%' || (SELECT query_text FROM q) || '%')
                            THEN 1.0
                            ELSE 0.0
                        END AS exact_score
                    FROM merged
                    ORDER BY (
                        COALESCE(vector_score, 0.0) * 0.72
                        + LEAST(COALESCE(lexical_score, 0.0), 1.0) * 0.18
                        + CASE
                            WHEN lower(search_text) LIKE ('%' || (SELECT query_text FROM q) || '%')
                            THEN 0.10
                            ELSE 0.0
                          END
                    ) DESC
                    LIMIT $5
                    """,
                    query_embedding_str,
                    query,
                    project_uuid,
                    candidate_limit,
                    candidate_limit,
                    list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
                )

        results: list[KnowledgeSearchResultView] = []
        query_tokens = self._query_tokens(query)
        query_lower = query.lower().strip()

        for row in rows:
            content = str(row["content"])
            raw_search_text = _optional_row_value(row, "search_text")
            search_text = str(raw_search_text or content)
            search_lower = search_text.lower()
            search_tokens = self._query_tokens(search_text)

            vector_score = (
                _optional_float(_optional_row_value(row, "vector_score")) or 0.0
            )
            lexical_score = (
                _optional_float(_optional_row_value(row, "lexical_score")) or 0.0
            )
            exact_score = (
                _optional_float(_optional_row_value(row, "exact_score")) or 0.0
            )

            token_overlap = 0.0
            if query_tokens:
                token_overlap = len(query_tokens & search_tokens) / len(query_tokens)

            rare_token_hits = sum(
                1
                for token in query_tokens
                if len(token) >= 5 and token in search_tokens
            )
            rare_token_bonus = min(0.24, rare_token_hits * 0.08)
            exact_phrase_bonus = (
                0.22 if query_lower and query_lower in search_lower else 0.0
            )
            lexical_bonus = min(0.35, lexical_score * 4.0)

            score = (
                vector_score * 0.48
                + lexical_bonus
                + exact_score * 0.20
                + token_overlap * 0.32
                + rare_token_bonus
                + exact_phrase_bonus
            )

            method = "hybrid"
            if lexical_score <= 0.0 and token_overlap <= 0.0:
                method = "vector"
            elif vector_score <= 0.0:
                method = "fts"

            source_refs = _source_ref_views_from_payload(
                _optional_row_value(row, "source_refs")
            )
            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=content,
                    score=score,
                    method=method,
                    document_id=_optional_row_text(row, "document_id"),
                    source=_optional_row_text(row, "source"),
                    document_status=_optional_row_text(row, "document_status"),
                    entry_kind=_optional_row_text(row, "entry_kind"),
                    title=_optional_row_text(row, "title"),
                    source_excerpt=_first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    embedding_text=_optional_row_text(row, "embedding_text"),
                    questions=_optional_row_value(row, "questions"),
                    synonyms=_optional_row_value(row, "synonyms"),
                    tags=_optional_row_value(row, "tags"),
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
                """
                WITH q AS (
                    SELECT
                        websearch_to_tsquery('russian', $1) AS query_ts,
                        lower($1) AS query_text
                ),
                scored AS (
                    SELECT
                        rs.entry_id AS id,
                        rs.answer AS content,
                        rs.document_id,
                        d.file_name AS source,
                        d.status AS document_status,
                        rs.entry_kind,
                        rs.title,
                        rs.source_refs,
                        rs.embedding_text,
                        rs.enrichment->'questions' AS questions,
                        rs.enrichment->'synonyms' AS synonyms,
                        rs.enrichment->'tags' AS tags,
                        rs.search_text,
                        ts_rank_cd(
                            to_tsvector('russian', COALESCE(rs.search_text, '')),
                            q.query_ts
                        ) AS lexical_score,
                        (
                            SELECT COUNT(DISTINCT token)::double precision
                            FROM regexp_split_to_table(q.query_text, '[^[:alnum:]а-яё]+') AS token
                            WHERE length(token) >= 4
                              AND lower(rs.search_text) LIKE '%' || token || '%'
                        ) AS token_overlap
                    FROM knowledge_retrieval_surface AS rs
                    LEFT JOIN knowledge_documents AS d ON d.id = rs.document_id,
                    q
                    WHERE rs.project_id = $2
                      AND rs.entry_kind = ANY($4::text[])
                      AND rs.status = 'published'
                      AND rs.visibility = 'runtime'
                      AND (d.status = 'processed' OR d.status IS NULL)
                )
                SELECT
                    id,
                    content,
                    document_id,
                    source,
                    document_status,
                    entry_kind,
                    title,
                    source_refs,
                    embedding_text,
                    questions,
                    synonyms,
                    tags,
                    search_text,
                    (
                        lexical_score
                        + (token_overlap * 0.06)
                        + CASE
                            WHEN COALESCE(title, '') <> ''
                            THEN 0.05::double precision
                            ELSE 0.0::double precision
                          END
                    ) AS score
                FROM scored
                WHERE lexical_score > 0.0
                   OR token_overlap > 0.0
                ORDER BY score DESC
                LIMIT $3
                """,
                normalized_query,
                ensure_uuid(project_id),
                candidate_limit,
                list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS),
            )

        results: list[KnowledgeSearchResultView] = []
        for row in rows:
            source_refs = _source_ref_views_from_payload(
                _optional_row_value(row, "source_refs")
            )
            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=str(row["content"]),
                    score=max(
                        0.0,
                        float(row["score"] or 0.0)
                        + self._keyword_overlap(normalized_query, str(row["content"]))
                        * 0.05,
                    ),
                    method="retrieval_surface_lexical",
                    document_id=_optional_row_text(row, "document_id"),
                    source=_optional_row_text(row, "source"),
                    document_status=_optional_row_text(row, "document_status"),
                    entry_kind=_optional_row_text(row, "entry_kind"),
                    title=_optional_row_text(row, "title"),
                    source_excerpt=_first_source_excerpt(source_refs),
                    source_refs=source_refs,
                    embedding_text=_optional_row_text(row, "embedding_text"),
                    questions=_optional_row_value(row, "questions"),
                    synonyms=_optional_row_value(row, "synonyms"),
                    tags=_optional_row_value(row, "tags"),
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def create_compiler_run(self, run: CompilerRun) -> None:
        metrics_payload = _stage_e_metrics_payload(run.metrics)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO knowledge_compiler_runs (
                        id,
                        project_id,
                        document_id,
                        mode,
                        compiler_version,
                        prompt_version,
                        model,
                        status,
                        error,
                        started_at,
                        finished_at,
                        created_by
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        mode = EXCLUDED.mode,
                        compiler_version = EXCLUDED.compiler_version,
                        prompt_version = EXCLUDED.prompt_version,
                        model = EXCLUDED.model,
                        status = EXCLUDED.status,
                        error = EXCLUDED.error,
                        started_at = EXCLUDED.started_at,
                        finished_at = EXCLUDED.finished_at,
                        created_by = EXCLUDED.created_by,
                        updated_at = now()
                    """,
                    run.id,
                    ensure_uuid(run.project_id),
                    ensure_uuid(run.document_id),
                    run.mode,
                    run.compiler_version,
                    run.prompt_version,
                    run.model,
                    run.status.value,
                    run.error,
                    run.started_at,
                    run.finished_at,
                    run.created_by,
                )
                await self._upsert_compilation_metrics(
                    conn=conn,
                    compiler_run_id=run.id,
                    metrics=run.metrics,
                    metrics_payload=metrics_payload,
                )

    async def complete_compiler_run(
        self,
        compiler_run_id: str,
        metrics: CompilationMetrics,
    ) -> None:
        metrics_payload = _stage_e_metrics_payload(metrics)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE knowledge_compiler_runs
                    SET status = 'completed',
                        error = '',
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = $1
                    """,
                    compiler_run_id,
                )
                await self._upsert_compilation_metrics(
                    conn=conn,
                    compiler_run_id=compiler_run_id,
                    metrics=metrics,
                    metrics_payload=metrics_payload,
                )

    async def fail_compiler_run(
        self,
        compiler_run_id: str,
        error: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_compiler_runs
                SET status = 'failed',
                    error = $2,
                    finished_at = now(),
                    updated_at = now()
                WHERE id = $1
                """,
                compiler_run_id,
                error,
            )

    async def _upsert_compilation_metrics(
        self,
        *,
        conn: asyncpg.Connection,
        compiler_run_id: str,
        metrics: CompilationMetrics,
        metrics_payload: Mapping[str, object],
    ) -> None:
        await conn.execute(
            """
            INSERT INTO knowledge_compilation_metrics (
                compiler_run_id,
                source_chunk_count,
                answer_candidate_count,
                grounded_candidate_count,
                rejected_candidate_count,
                candidate_cluster_count,
                canonical_entry_count,
                enriched_entry_count,
                embedded_entry_count,
                published_entry_count,
                fallback_row_count,
                dropped_forbidden_count,
                entries_without_source_refs_count,
                metrics
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
                $14::jsonb
            )
            ON CONFLICT (compiler_run_id)
            DO UPDATE SET
                source_chunk_count = EXCLUDED.source_chunk_count,
                answer_candidate_count = EXCLUDED.answer_candidate_count,
                grounded_candidate_count = EXCLUDED.grounded_candidate_count,
                rejected_candidate_count = EXCLUDED.rejected_candidate_count,
                candidate_cluster_count = EXCLUDED.candidate_cluster_count,
                canonical_entry_count = EXCLUDED.canonical_entry_count,
                enriched_entry_count = EXCLUDED.enriched_entry_count,
                embedded_entry_count = EXCLUDED.embedded_entry_count,
                published_entry_count = EXCLUDED.published_entry_count,
                fallback_row_count = EXCLUDED.fallback_row_count,
                dropped_forbidden_count = EXCLUDED.dropped_forbidden_count,
                entries_without_source_refs_count = EXCLUDED.entries_without_source_refs_count,
                metrics = EXCLUDED.metrics,
                updated_at = now()
            """,
            compiler_run_id,
            metrics.source_chunk_count,
            metrics.answer_candidate_count,
            metrics.grounded_candidate_count,
            metrics.rejected_candidate_count,
            metrics.candidate_cluster_count,
            metrics.canonical_entry_count,
            metrics.enriched_entry_count,
            metrics.embedded_entry_count,
            metrics.published_entry_count,
            metrics.fallback_row_count,
            metrics.dropped_forbidden_count,
            metrics.entries_without_source_refs_count,
            _jsonb_object(metrics_payload),
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
                for candidate in candidates:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_answer_candidates (
                            id,
                            project_id,
                            document_id,
                            compiler_run_id,
                            topic_key,
                            title,
                            candidate_answer,
                            source_refs,
                            confidence,
                            status,
                            rejection_reason,
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
                            $8::jsonb,
                            $9,
                            $10,
                            $11,
                            $12::jsonb
                        )
                        ON CONFLICT (id)
                        DO UPDATE SET
                            topic_key = EXCLUDED.topic_key,
                            title = EXCLUDED.title,
                            candidate_answer = EXCLUDED.candidate_answer,
                            source_refs = EXCLUDED.source_refs,
                            confidence = EXCLUDED.confidence,
                            status = EXCLUDED.status,
                            rejection_reason = EXCLUDED.rejection_reason,
                            metadata = EXCLUDED.metadata
                        """,
                        candidate.id,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id),
                        candidate.compiler_run_id,
                        candidate.topic_key,
                        candidate.title,
                        candidate.candidate_answer,
                        _stage_e_jsonb_array(
                            _stage_e_candidate_source_refs_payload(candidate)
                        ),
                        candidate.confidence,
                        candidate.status.value,
                        candidate.rejection_reason,
                        _jsonb_object(candidate.metadata),
                    )

        return len(candidates)

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
                for cluster in clusters:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_candidate_clusters (
                            id,
                            project_id,
                            document_id,
                            compiler_run_id,
                            cluster_key,
                            topic,
                            status,
                            merge_strategy,
                            merge_reason,
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
                            $10::jsonb
                        )
                        ON CONFLICT (id)
                        DO UPDATE SET
                            cluster_key = EXCLUDED.cluster_key,
                            topic = EXCLUDED.topic,
                            status = EXCLUDED.status,
                            merge_strategy = EXCLUDED.merge_strategy,
                            merge_reason = EXCLUDED.merge_reason,
                            metadata = EXCLUDED.metadata
                        """,
                        cluster.id,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id),
                        cluster.compiler_run_id,
                        cluster.cluster_key,
                        cluster.topic,
                        cluster.status.value,
                        cluster.merge_strategy,
                        cluster.merge_reason,
                        _jsonb_object(cluster.metadata),
                    )

                    await conn.execute(
                        """
                        DELETE FROM knowledge_candidate_cluster_members
                        WHERE cluster_id = $1
                        """,
                        cluster.id,
                    )

                    for candidate_index, candidate_id in enumerate(
                        cluster.candidate_ids
                    ):
                        await conn.execute(
                            """
                            INSERT INTO knowledge_candidate_cluster_members (
                                cluster_id,
                                candidate_id,
                                candidate_index
                            )
                            VALUES ($1, $2, $3)
                            ON CONFLICT (cluster_id, candidate_id)
                            DO UPDATE SET
                                candidate_index = EXCLUDED.candidate_index
                            """,
                            cluster.id,
                            candidate_id,
                            candidate_index,
                        )

        return len(clusters)

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

        for batch in _batched_canonical_entries(
            entries, settings.KNOWLEDGE_EMBED_BATCH_SIZE
        ):
            texts = [_entry_embedding_text(entry) for entry in batch]
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
                        enrichment_payload = _enrichment_payload(entry)
                        source_refs_payload = _source_refs_payload(entry)
                        embedding_text = _entry_embedding_text(entry)
                        embedding_text_version = _entry_embedding_text_version(entry)

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
                            _jsonb_object(enrichment_payload),
                            _jsonb_object(entry.metadata),
                        )

                        await conn.execute(
                            "DELETE FROM knowledge_entry_source_refs WHERE entry_id = $1",
                            entry_uuid,
                        )

                        for source_ref in entry.source_refs:
                            if source_ref.source_chunk_id is None:
                                continue
                            await conn.execute(
                                """
                                INSERT INTO knowledge_entry_source_refs (
                                    entry_id,
                                    source_chunk_id,
                                    source_index,
                                    quote,
                                    start_offset,
                                    end_offset,
                                    confidence,
                                    metadata
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, $7, '{}'::jsonb)
                                """,
                                entry_uuid,
                                source_ref.source_chunk_id,
                                source_ref.source_index or 0,
                                source_ref.quote,
                                source_ref.start_offset,
                                source_ref.end_offset,
                                source_ref.confidence,
                            )

                        await conn.execute(
                            "DELETE FROM knowledge_retrieval_surface WHERE entry_id = $1",
                            entry_uuid,
                        )

                        if entry.is_published_runtime_entry:
                            await conn.execute(
                                """
                                INSERT INTO knowledge_retrieval_surface (
                                    project_id,
                                    document_id,
                                    entry_id,
                                    stable_key,
                                    entry_kind,
                                    title,
                                    answer,
                                    embedding_text,
                                    embedding_text_version,
                                    embedding,
                                    search_text,
                                    enrichment,
                                    source_refs,
                                    metadata,
                                    status,
                                    visibility
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
                                    $10::vector,
                                    $11,
                                    $12::jsonb,
                                    $13::jsonb,
                                    $14::jsonb,
                                    'published',
                                    'runtime'
                                )
                                ON CONFLICT (entry_id)
                                DO UPDATE SET
                                    stable_key = EXCLUDED.stable_key,
                                    entry_kind = EXCLUDED.entry_kind,
                                    title = EXCLUDED.title,
                                    answer = EXCLUDED.answer,
                                    embedding_text = EXCLUDED.embedding_text,
                                    embedding_text_version = EXCLUDED.embedding_text_version,
                                    embedding = EXCLUDED.embedding,
                                    search_text = EXCLUDED.search_text,
                                    enrichment = EXCLUDED.enrichment,
                                    source_refs = EXCLUDED.source_refs,
                                    metadata = EXCLUDED.metadata,
                                    updated_at = now()
                                """,
                                ensure_uuid(project_id),
                                ensure_uuid(document_id),
                                entry_uuid,
                                entry.stable_key,
                                entry.entry_kind.value,
                                entry.title,
                                entry.answer,
                                embedding_text,
                                embedding_text_version,
                                _pg_vector_text(embeddings[index]),
                                _surface_search_text(entry),
                                _jsonb_object(enrichment_payload),
                                json.dumps(source_refs_payload, ensure_ascii=False),
                                _jsonb_object(entry.metadata),
                            )

        return len(entries)

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
                await conn.execute(
                    "DELETE FROM knowledge_source_chunks WHERE document_id = $1",
                    ensure_uuid(document_id),
                )

                for chunk in chunks:
                    await conn.execute(
                        """
                        INSERT INTO knowledge_source_chunks (
                            id,
                            project_id,
                            document_id,
                            source_index,
                            content,
                            page,
                            section_title,
                            start_offset,
                            end_offset,
                            checksum,
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
                            $11::jsonb
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            project_id = EXCLUDED.project_id,
                            document_id = EXCLUDED.document_id,
                            source_index = EXCLUDED.source_index,
                            content = EXCLUDED.content,
                            page = EXCLUDED.page,
                            section_title = EXCLUDED.section_title,
                            start_offset = EXCLUDED.start_offset,
                            end_offset = EXCLUDED.end_offset,
                            checksum = EXCLUDED.checksum,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """,
                        chunk.id,
                        ensure_uuid(project_id),
                        ensure_uuid(document_id),
                        chunk.source_index,
                        chunk.content,
                        chunk.page,
                        chunk.section_title,
                        chunk.start_offset,
                        chunk.end_offset,
                        chunk.checksum or None,
                        _jsonb_object(chunk.metadata),
                    )

        return len(chunks)

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
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_documents (project_id, file_name, file_size, uploaded_by)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
                ensure_uuid(project_id),
                file_name,
                file_size,
                uploaded_by,
            )

        document_id = str(row["id"])
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
            rows = await conn.fetch(
                """
                SELECT
                    d.id,
                    d.file_name,
                    d.file_size,
                    d.status,
                    d.error,
                    d.uploaded_by,
                    d.created_at,
                    d.updated_at,
                    d.preprocessing_mode,
                    d.preprocessing_status,
                    d.preprocessing_error,
                    d.preprocessing_model,
                    d.preprocessing_prompt_version,
                    d.preprocessing_metrics,
                    COUNT(DISTINCT ke.id)::int AS entry_count,
                    COUNT(DISTINCT rs.entry_id)::int AS runtime_entry_count
                FROM knowledge_documents AS d
                LEFT JOIN knowledge_entries AS ke ON ke.document_id = d.id
                LEFT JOIN knowledge_retrieval_surface AS rs ON rs.entry_id = ke.id
                WHERE d.project_id = $1
                GROUP BY
                    d.id,
                    d.file_name,
                    d.file_size,
                    d.status,
                    d.error,
                    d.uploaded_by,
                    d.created_at,
                    d.updated_at,
                    d.preprocessing_mode,
                    d.preprocessing_status,
                    d.preprocessing_error,
                    d.preprocessing_model,
                    d.preprocessing_prompt_version,
                    d.preprocessing_metrics
                ORDER BY d.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                ensure_uuid(project_id),
                limit,
                offset,
            )

        documents = [
            KnowledgeDocumentView(
                id=str(row["id"]),
                file_name=str(row["file_name"]),
                file_size=int(row["file_size"])
                if row["file_size"] is not None
                else None,
                status=str(row["status"]),
                error=str(row["error"]) if row["error"] is not None else None,
                uploaded_by=str(row["uploaded_by"])
                if row["uploaded_by"] is not None
                else None,
                created_at=_normalize_timestamp(row["created_at"]),
                updated_at=_normalize_timestamp(row["updated_at"]),
                chunk_count=int(row["entry_count"] or 0),
                preprocessing_mode=str(row["preprocessing_mode"])
                if row["preprocessing_mode"] is not None
                else None,
                preprocessing_status=str(row["preprocessing_status"])
                if row["preprocessing_status"] is not None
                else None,
                preprocessing_error=str(row["preprocessing_error"])
                if row["preprocessing_error"] is not None
                else None,
                preprocessing_model=str(row["preprocessing_model"])
                if row["preprocessing_model"] is not None
                else None,
                preprocessing_prompt_version=str(row["preprocessing_prompt_version"])
                if row["preprocessing_prompt_version"] is not None
                else None,
                preprocessing_metrics=row["preprocessing_metrics"],
                structured_entries=int(row["runtime_entry_count"] or 0),
                structured_chunk_count=int(row["runtime_entry_count"] or 0),
            )
            for row in rows or []
        ]

        logger.debug("Retrieved knowledge documents", extra={"count": len(documents)})
        return documents

    async def get_document(
        self, document_id: str
    ) -> KnowledgeDocumentDetailView | None:
        logger.debug("Fetching knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    project_id,
                    file_name,
                    file_size,
                    status,
                    error,
                    uploaded_by,
                    created_at,
                    updated_at,
                    preprocessing_mode,
                    preprocessing_status,
                    preprocessing_error,
                    preprocessing_model,
                    preprocessing_prompt_version,
                    preprocessing_metrics
                FROM knowledge_documents
                WHERE id = $1
                """,
                ensure_uuid(document_id),
            )

            if not row:
                return None

            counts = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT ke.id)::int AS entry_count,
                    COUNT(DISTINCT rs.entry_id)::int AS runtime_entry_count
                FROM knowledge_entries AS ke
                LEFT JOIN knowledge_retrieval_surface AS rs ON rs.entry_id = ke.id
                WHERE ke.document_id = $1
                """,
                row["id"],
            )
            entry_count = int(counts["entry_count"] or 0) if counts else 0
            runtime_entry_count = (
                int(counts["runtime_entry_count"] or 0) if counts else 0
            )

        return KnowledgeDocumentDetailView(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            file_name=str(row["file_name"]),
            file_size=int(row["file_size"]) if row["file_size"] is not None else None,
            status=str(row["status"]),
            error=str(row["error"]) if row["error"] is not None else None,
            uploaded_by=str(row["uploaded_by"])
            if row["uploaded_by"] is not None
            else None,
            created_at=_normalize_timestamp(row["created_at"]),
            updated_at=_normalize_timestamp(row["updated_at"]),
            chunk_count=entry_count,
            preprocessing_mode=str(row["preprocessing_mode"])
            if row["preprocessing_mode"] is not None
            else None,
            preprocessing_status=str(row["preprocessing_status"])
            if row["preprocessing_status"] is not None
            else None,
            preprocessing_error=str(row["preprocessing_error"])
            if row["preprocessing_error"] is not None
            else None,
            preprocessing_model=str(row["preprocessing_model"])
            if row["preprocessing_model"] is not None
            else None,
            preprocessing_prompt_version=str(row["preprocessing_prompt_version"])
            if row["preprocessing_prompt_version"] is not None
            else None,
            preprocessing_metrics=row["preprocessing_metrics"],
            structured_entries=runtime_entry_count,
            structured_chunk_count=runtime_entry_count,
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
            await conn.execute(
                """
                UPDATE knowledge_documents
                SET status = $1, error = $2, updated_at = NOW()
                WHERE id = $3
            """,
                status,
                error,
                ensure_uuid(document_id),
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
            await conn.execute(
                """
                UPDATE knowledge_documents
                SET preprocessing_mode = $1,
                    preprocessing_status = $2,
                    preprocessing_error = $3,
                    preprocessing_model = COALESCE($4, preprocessing_model),
                    preprocessing_prompt_version = COALESCE($5, preprocessing_prompt_version),
                    preprocessing_metrics = COALESCE($6::jsonb, preprocessing_metrics),
                    updated_at = NOW()
                WHERE id = $7
                """,
                mode,
                status,
                error,
                model,
                prompt_version,
                json.dumps(metrics, ensure_ascii=False)
                if metrics is not None
                else None,
                ensure_uuid(document_id),
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

    @staticmethod
    def _stage_h_json_object(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items()}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return {str(key): item for key, item in parsed.items()}
        return {}

    @staticmethod
    def _stage_h_text_list(value: object) -> list[str]:
        if isinstance(value, str):
            text = " ".join(value.strip().split())
            return [text] if text else []
        if not isinstance(value, list):
            return []

        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @classmethod
    def _stage_h_entry_snapshot(cls, row: asyncpg.Record) -> dict[str, object]:
        return {
            "id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "document_id": str(row["document_id"]) if row["document_id"] else None,
            "compiler_run_id": str(row["compiler_run_id"] or ""),
            "stable_key": str(row["stable_key"]),
            "entry_kind": str(row["entry_kind"]),
            "title": str(row["title"]),
            "answer": str(row["answer"]),
            "status": str(row["status"]),
            "visibility": str(row["visibility"]),
            "version": int(row["version"]),
            "compiler_version": str(row["compiler_version"] or ""),
            "embedding_text": str(row["embedding_text"] or ""),
            "embedding_text_version": str(row["embedding_text_version"] or ""),
            "enrichment": cls._stage_h_json_object(row["enrichment"]),
            "metadata": cls._stage_h_json_object(row["metadata"]),
        }

    @classmethod
    def _stage_h_attached_questions(
        cls,
        *,
        enrichment: dict[str, object],
        metadata: dict[str, object],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for key in ("questions", "positive_questions", "synonyms", "tags"):
            for value in cls._stage_h_text_list(enrichment.get(key)):
                if value not in seen:
                    seen.add(value)
                    result.append(value)

        stage_h = cls._stage_h_json_object(metadata.get("stage_h"))
        raw_attached = stage_h.get("attached_questions")
        if isinstance(raw_attached, list):
            for item in raw_attached:
                if not isinstance(item, dict):
                    continue
                question = " ".join(str(item.get("question") or "").strip().split())
                if question and question not in seen:
                    seen.add(question)
                    result.append(question)

        return result

    @classmethod
    def _stage_h_embedding_text(cls, row: asyncpg.Record) -> str:
        enrichment = cls._stage_h_json_object(row["enrichment"])
        metadata = cls._stage_h_json_object(row["metadata"])
        parts = [
            str(row["title"] or "").strip(),
            str(row["answer"] or "").strip(),
            str(row["embedding_text"] or "").strip(),
            *cls._stage_h_attached_questions(enrichment=enrichment, metadata=metadata),
        ]

        result: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = " ".join(part.split())
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)

        return "\n".join(result)

    @staticmethod
    def _stage_h_search_text(
        *,
        title: str,
        answer: str,
        embedding_text: str,
    ) -> str:
        parts = (title, answer, embedding_text)
        result: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = " ".join(part.strip().split())
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return "\n".join(result)

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
            existing = await conn.fetchrow(
                """
                SELECT id, status
                FROM knowledge_edit_actions
                WHERE source_result_id = $1
                  AND action_index = $2
                """,
                source_result_id,
                action_index,
            )
            if existing is not None:
                return {"id": str(existing["id"]), "status": str(existing["status"])}

            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edit_actions (
                    id,
                    project_id,
                    document_id,
                    source_result_id,
                    source_run_id,
                    source_question_id,
                    action_index,
                    actor_user_id,
                    action_type,
                    target_entry_id,
                    reason,
                    payload
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
                    $12::jsonb
                )
                RETURNING id, status
                """,
                action_id,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
                source_result_id,
                source_run_id,
                source_question_id,
                action_index,
                actor_user_id,
                action_type,
                ensure_uuid(target_entry_id) if target_entry_id else None,
                reason,
                json.dumps(payload, ensure_ascii=False),
            )

        if row is None:
            raise RuntimeError("Failed to create knowledge edit action")

        return {"id": str(row["id"]), "status": str(row["status"])}

    async def mark_knowledge_edit_action_applied(
        self,
        action_id: str,
        *,
        result_payload: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_edit_actions
                SET status = 'applied',
                    error = '',
                    result_payload = $2::jsonb,
                    applied_at = COALESCE(applied_at, now()),
                    updated_at = now()
                WHERE id = $1
                """,
                action_id,
                json.dumps(result_payload or {}, ensure_ascii=False),
            )

    async def mark_knowledge_edit_action_rejected(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_edit_actions
                SET status = 'rejected',
                    error = $2,
                    result_payload = $3::jsonb,
                    updated_at = now()
                WHERE id = $1
                """,
                action_id,
                error,
                json.dumps(result_payload or {}, ensure_ascii=False),
            )

    async def mark_knowledge_edit_action_failed(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_edit_actions
                SET status = 'failed',
                    error = $2,
                    result_payload = $3::jsonb,
                    updated_at = now()
                WHERE id = $1
                """,
                action_id,
                error,
                json.dumps(result_payload or {}, ensure_ascii=False),
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
        question_text = " ".join(question.strip().split())
        if not question_text:
            raise ValueError("attach_question_to_entry requires non-empty question")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    """
                    SELECT
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
                    FROM knowledge_entries
                    WHERE id = $1
                      AND project_id = $2
                      AND document_id = $3
                    FOR UPDATE
                    """,
                    ensure_uuid(target_entry_id),
                    ensure_uuid(project_id),
                    ensure_uuid(document_id),
                )
                if before is None:
                    raise ValueError("target knowledge entry not found")

                previous_snapshot = self._stage_h_entry_snapshot(before)
                previous_version = int(before["version"])

                metadata = self._stage_h_json_object(before["metadata"])
                enrichment = self._stage_h_json_object(before["enrichment"])

                stage_h = self._stage_h_json_object(metadata.get("stage_h"))
                raw_attached = stage_h.get("attached_questions")
                attached: list[dict[str, object]] = []
                if isinstance(raw_attached, list):
                    attached = [
                        {str(key): value for key, value in item.items()}
                        for item in raw_attached
                        if isinstance(item, dict)
                    ]

                if not any(item.get("question") == question_text for item in attached):
                    attached.append(
                        {
                            "question": question_text,
                            "action_id": action_id,
                            "reason": reason,
                            "actor_user_id": actor_user_id,
                        }
                    )

                stage_h["attached_questions"] = attached
                metadata["stage_h"] = stage_h

                for key in ("questions", "positive_questions"):
                    values = self._stage_h_text_list(enrichment.get(key))
                    if question_text not in values:
                        values.append(question_text)
                    enrichment[key] = values

                next_version = previous_version + 1

                await conn.execute(
                    """
                    UPDATE knowledge_entries
                    SET enrichment = $2::jsonb,
                        metadata = $3::jsonb,
                        version = $4,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    ensure_uuid(target_entry_id),
                    json.dumps(enrichment, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    next_version,
                )

                await conn.execute(
                    """
                    UPDATE knowledge_retrieval_surface
                    SET enrichment = $2::jsonb,
                        metadata = $3::jsonb,
                        updated_at = now()
                    WHERE entry_id = $1
                    """,
                    ensure_uuid(target_entry_id),
                    json.dumps(enrichment, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                )

                after = await conn.fetchrow(
                    """
                    SELECT
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
                    FROM knowledge_entries
                    WHERE id = $1
                    """,
                    ensure_uuid(target_entry_id),
                )
                if after is None:
                    raise RuntimeError(
                        "target knowledge entry disappeared after update"
                    )

                await conn.execute(
                    """
                    INSERT INTO knowledge_entry_versions (
                        entry_id,
                        project_id,
                        document_id,
                        action_id,
                        from_version,
                        to_version,
                        previous_snapshot,
                        new_snapshot
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                    """,
                    ensure_uuid(target_entry_id),
                    ensure_uuid(project_id),
                    ensure_uuid(document_id),
                    action_id,
                    previous_version,
                    next_version,
                    json.dumps(previous_snapshot, ensure_ascii=False),
                    json.dumps(self._stage_h_entry_snapshot(after), ensure_ascii=False),
                )

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
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
                FROM knowledge_entries
                WHERE id = $1
                  AND project_id = $2
                  AND document_id = $3
                """,
                ensure_uuid(target_entry_id),
                ensure_uuid(project_id),
                ensure_uuid(document_id),
            )

        if row is None:
            raise ValueError("target knowledge entry not found")

        embedding_text = self._stage_h_embedding_text(row)
        if not embedding_text.strip():
            raise ValueError("cannot rebuild embedding from empty entry text")

        embedding_result = await embed_batch([embedding_text])
        if not embedding_result.embeddings:
            raise RuntimeError("embedding provider returned no vectors")

        if embedding_result.usage is not None:
            await self._usage_repo.record_event(
                ModelUsageEventCreate.from_measurement(
                    project_id=project_id,
                    source="knowledge_edit_action",
                    measurement=embedding_result.usage,
                    document_id=document_id,
                )
            )

        embedding_text_version = "entry_embedding_text_v2_stage_h"
        search_text = self._stage_h_search_text(
            title=str(row["title"]),
            answer=str(row["answer"]),
            embedding_text=embedding_text,
        )

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    """
                    SELECT
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
                    FROM knowledge_entries
                    WHERE id = $1
                      AND project_id = $2
                      AND document_id = $3
                    FOR UPDATE
                    """,
                    ensure_uuid(target_entry_id),
                    ensure_uuid(project_id),
                    ensure_uuid(document_id),
                )
                if before is None:
                    raise ValueError("target knowledge entry not found")

                previous_snapshot = self._stage_h_entry_snapshot(before)
                entry_version = int(before["version"])

                await conn.execute(
                    """
                    UPDATE knowledge_entries
                    SET embedding_text = $2,
                        embedding_text_version = $3,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    ensure_uuid(target_entry_id),
                    embedding_text,
                    embedding_text_version,
                )

                await conn.execute(
                    """
                    UPDATE knowledge_retrieval_surface
                    SET embedding_text = $2,
                        embedding_text_version = $3,
                        embedding = $4::vector,
                        search_text = $5,
                        updated_at = now()
                    WHERE entry_id = $1
                    """,
                    ensure_uuid(target_entry_id),
                    embedding_text,
                    embedding_text_version,
                    _pg_vector_text(embedding_result.embeddings[0]),
                    search_text,
                )

                after = await conn.fetchrow(
                    """
                    SELECT
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
                    FROM knowledge_entries
                    WHERE id = $1
                    """,
                    ensure_uuid(target_entry_id),
                )
                if after is None:
                    raise RuntimeError(
                        "target knowledge entry disappeared after embedding rebuild"
                    )

                await conn.execute(
                    """
                    INSERT INTO knowledge_entry_versions (
                        entry_id,
                        project_id,
                        document_id,
                        action_id,
                        from_version,
                        to_version,
                        previous_snapshot,
                        new_snapshot
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                    """,
                    ensure_uuid(target_entry_id),
                    ensure_uuid(project_id),
                    ensure_uuid(document_id),
                    action_id,
                    entry_version,
                    entry_version,
                    json.dumps(previous_snapshot, ensure_ascii=False),
                    json.dumps(self._stage_h_entry_snapshot(after), ensure_ascii=False),
                )

    async def delete_document_chunks(self, document_id: str) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM knowledge_retrieval_surface WHERE document_id = $1",
                    ensure_uuid(document_id),
                )
                await conn.execute(
                    "DELETE FROM knowledge_entries WHERE document_id = $1",
                    ensure_uuid(document_id),
                )
                await conn.execute(
                    "DELETE FROM knowledge_compiler_runs WHERE document_id = $1",
                    ensure_uuid(document_id),
                )
                await conn.execute(
                    "DELETE FROM knowledge_source_chunks WHERE document_id = $1",
                    ensure_uuid(document_id),
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
