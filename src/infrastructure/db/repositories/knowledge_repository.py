"""
Knowledge repository for RAG with hybrid search.

Clean Architecture contract:
- DB rows are converted to explicit typed read views inside this repository.
- Repository read methods do not return dict/Mapping compatibility objects.
"""

import json
import re
from collections.abc import Iterator
from typing import Protocol

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
    KnowledgeSearchResultView,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.llm.embedding_service import embed_batch, embed_text
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.utils.uuid_utils import ensure_uuid


logger = get_logger(__name__)


class _RowLookup(Protocol):
    def __getitem__(self, key: str) -> object: ...


def _optional_row_text(row: _RowLookup, key: str) -> str | None:
    try:
        value = row[key]
    except KeyError:
        return None

    return str(value) if value is not None else None


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
    if not isinstance(value, list):
        value = []
    return json.dumps(value, ensure_ascii=False)


def _pg_vector_text(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _batched_chunks(
    chunks: list[JsonObject], batch_size: int
) -> Iterator[list[JsonObject]]:
    for start in range(0, len(chunks), batch_size):
        yield chunks[start : start + batch_size]


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
        query_embedding_str = (
            "[" + ",".join(str(x) for x in query_embedding_result.embedding) + "]"
        )
        project_uuid = ensure_uuid(project_id)
        # First-stage retrieval must be broad enough for hybrid ranking.
        # Ranking cannot rescue a relevant chunk that never entered the candidate set.
        candidate_limit = max(limit * 20, 80)

        if query_embedding_result.usage is not None:
            await self._usage_repo.record_event(
                ModelUsageEventCreate.from_measurement(
                    project_id=project_id,
                    source="rag_search",
                    measurement=query_embedding_result.usage,
                    thread_id=thread_id,
                )
            )

        # Wider candidate pool matters more than tiny top-N changes.
        # For small KBs this is cheap; for larger KBs it gives ranking enough room.
        candidate_limit = max(limit * 10, 50)

        async with self.pool.acquire() as conn:
            if not hybrid_fallback:
                rows = await conn.fetch(
                    """
                    SELECT
                        kb.id,
                        kb.content,
                        kb.document_id,
                        d.file_name AS source,
                        d.status AS document_status,
                        COALESCE(kb.embedding_text, kb.content, '') AS search_text,
                        (1 - (kb.embedding <=> $1::vector)) AS vector_score,
                        0.0::double precision AS lexical_score,
                        0.0::double precision AS exact_score,
                        (1 - (kb.embedding <=> $1::vector)) AS combined_score
                    FROM knowledge_base AS kb
                    LEFT JOIN knowledge_documents AS d ON d.id = kb.document_id
                    WHERE kb.project_id = $2
                      AND kb.embedding IS NOT NULL
                      AND (d.status = 'processed' OR d.status IS NULL)
                    ORDER BY kb.embedding <=> $1::vector
                    LIMIT $3
                    """,
                    query_embedding_str,
                    project_uuid,
                    limit,
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
                            kb.id,
                            kb.content,
                            kb.document_id,
                            d.file_name AS source,
                            d.status AS document_status,
                            trim(concat_ws(
                                E'\n',
                                kb.title,
                                kb.entry_type,
                                kb.embedding_text,
                                kb.source_excerpt,
                                kb.content,
                                CASE
                                    WHEN jsonb_typeof(kb.questions) = 'array'
                                    THEN (
                                        SELECT string_agg(value, ' ')
                                        FROM jsonb_array_elements_text(kb.questions) AS value
                                    )
                                    ELSE ''
                                END,
                                CASE
                                    WHEN jsonb_typeof(kb.synonyms) = 'array'
                                    THEN (
                                        SELECT string_agg(value, ' ')
                                        FROM jsonb_array_elements_text(kb.synonyms) AS value
                                    )
                                    ELSE ''
                                END,
                                CASE
                                    WHEN jsonb_typeof(kb.tags) = 'array'
                                    THEN (
                                        SELECT string_agg(value, ' ')
                                        FROM jsonb_array_elements_text(kb.tags) AS value
                                    )
                                    ELSE ''
                                END
                            )) AS search_text,
                            kb.embedding
                        FROM knowledge_base AS kb
                        LEFT JOIN knowledge_documents AS d ON d.id = kb.document_id
                        WHERE kb.project_id = $3
                          AND kb.embedding IS NOT NULL
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
                        search_text,
                        vector_score,
                        lexical_score,
                        CASE
                            WHEN lower(search_text) LIKE ('%' || (SELECT query_text FROM q) || '%')
                            THEN 1.0
                            ELSE 0.0
                        END AS exact_score,
                        (
                            COALESCE(vector_score, 0.0) * 0.72
                            + LEAST(COALESCE(lexical_score, 0.0), 1.0) * 0.18
                            + CASE
                                WHEN lower(search_text) LIKE ('%' || (SELECT query_text FROM q) || '%')
                                THEN 0.10
                                ELSE 0.0
                              END
                            + CASE
                                WHEN vector_rank IS NOT NULL
                                THEN 0.04 / (60.0 + vector_rank)
                                ELSE 0.0
                              END
                            + CASE
                                WHEN lexical_rank IS NOT NULL
                                THEN 0.04 / (60.0 + lexical_rank)
                                ELSE 0.0
                              END
                        ) AS combined_score
                    FROM merged
                    ORDER BY combined_score DESC
                    LIMIT $5
                    """,
                    query_embedding_str,
                    query,
                    project_uuid,
                    candidate_limit,
                    candidate_limit,
                )

        results: list[KnowledgeSearchResultView] = []
        query_tokens = self._query_tokens(query)
        query_lower = query.lower().strip()

        for row in rows:
            content = str(row["content"])
            try:
                raw_search_text = row["search_text"]
            except KeyError:
                raw_search_text = None
            search_text = str(raw_search_text or content)
            search_lower = search_text.lower()
            search_tokens = self._query_tokens(search_text)

            try:
                raw_vector_score = row["vector_score"]
            except KeyError:
                raw_vector_score = row["score"] if "score" in row else 0.0

            try:
                raw_lexical_score = row["lexical_score"]
            except KeyError:
                raw_lexical_score = 0.0

            try:
                raw_exact_score = row["exact_score"]
            except KeyError:
                raw_exact_score = 0.0

            vector_score = float(raw_vector_score or 0.0)
            lexical_score = float(raw_lexical_score or 0.0)
            exact_score = float(raw_exact_score or 0.0)

            token_overlap = 0.0
            if query_tokens:
                token_overlap = len(query_tokens & search_tokens) / len(query_tokens)

            # Rare/important query words should beat generic semantic similarity.
            # Example: "ночью", "подписку", "заменит", "стиль", "менеджер".
            rare_token_hits = 0
            for token in query_tokens:
                if len(token) >= 5 and token in search_tokens:
                    rare_token_hits += 1

            rare_token_bonus = min(0.24, rare_token_hits * 0.08)
            exact_phrase_bonus = (
                0.22 if query_lower and query_lower in search_lower else 0.0
            )

            # ts_rank values are often tiny, so normalize by amplification + cap.
            lexical_bonus = min(0.35, lexical_score * 4.0)

            # Final ranking:
            # - vector keeps semantic recall;
            # - lexical/token bonuses rescue precise domain markers;
            # - exact phrase catches FAQ-like chunks.
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

            results.append(
                KnowledgeSearchResultView(
                    id=str(row["id"]),
                    content=content,
                    score=score,
                    method=method,
                    document_id=_optional_row_text(row, "document_id"),
                    source=_optional_row_text(row, "source"),
                    document_status=_optional_row_text(row, "document_status"),
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

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    kb.id,
                    kb.content,
                    kb.document_id,
                    d.file_name AS source,
                    d.status AS document_status,
                    ts_rank_cd(kb.tsv, plainto_tsquery('russian', $1)) AS score
                FROM knowledge_documents AS d
                JOIN knowledge_base AS kb ON kb.document_id = d.id
                WHERE d.project_id = $2
                  AND d.status = 'processed'
                  AND kb.tsv @@ plainto_tsquery('russian', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query,
                ensure_uuid(project_id),
                limit,
            )

        results = [
            KnowledgeSearchResultView(
                id=str(row["id"]),
                content=str(row["content"]),
                score=float(row["score"])
                + self._keyword_overlap(query, str(row["content"])) * 0.15,
                method="fts",
                document_id=_optional_row_text(row, "document_id"),
                source=_optional_row_text(row, "source"),
                document_status=_optional_row_text(row, "document_status"),
            )
            for row in rows
        ]
        results.sort(key=lambda item: item.score, reverse=True)
        return results

    async def add_knowledge_batch(
        self,
        project_id: str,
        chunks: list[JsonObject],
        document_id: str | None = None,
    ) -> int:
        """Persist plain chunks using the legacy knowledge_base insert contract."""
        if not chunks:
            return 0

        for batch in _batched_chunks(chunks, settings.KNOWLEDGE_EMBED_BATCH_SIZE):
            texts = [str(chunk["content"]) for chunk in batch]
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
                    for index, chunk in enumerate(batch):
                        await conn.execute(
                            """
                            INSERT INTO knowledge_base (project_id, document_id, content, embedding)
                            VALUES ($1, $2, $3, $4::vector)
                            """,
                            ensure_uuid(project_id),
                            ensure_uuid(document_id) if document_id else None,
                            str(chunk["content"]),
                            _pg_vector_text(embeddings[index]),
                        )

        return len(chunks)

    async def add_structured_knowledge_batch(
        self,
        project_id: str,
        chunks: list[JsonObject],
        document_id: str | None = None,
    ) -> int:
        """Persist LLM-normalized structured knowledge entries."""
        if not chunks:
            return 0

        for batch in _batched_chunks(chunks, settings.KNOWLEDGE_EMBED_BATCH_SIZE):
            texts = [
                str(chunk.get("embedding_text") or chunk["content"]) for chunk in batch
            ]
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
                    for index, chunk in enumerate(batch):
                        await conn.execute(
                            """
                            INSERT INTO knowledge_base (
                                project_id,
                                document_id,
                                content,
                                embedding,
                                entry_type,
                                title,
                                source_excerpt,
                                questions,
                                synonyms,
                                tags,
                                embedding_text
                            )
                            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11)
                            """,
                            ensure_uuid(project_id),
                            ensure_uuid(document_id) if document_id else None,
                            str(chunk["content"]),
                            _pg_vector_text(embeddings[index]),
                            str(chunk.get("entry_type") or "chunk"),
                            str(chunk["title"])
                            if chunk.get("title") is not None
                            else None,
                            str(chunk["source_excerpt"])
                            if chunk.get("source_excerpt") is not None
                            else None,
                            _jsonb_array(chunk.get("questions")),
                            _jsonb_array(chunk.get("synonyms")),
                            _jsonb_array(chunk.get("tags")),
                            str(chunk["embedding_text"])
                            if chunk.get("embedding_text") is not None
                            else None,
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
                    COUNT(kb.id)::int AS chunk_count
                FROM knowledge_documents AS d
                LEFT JOIN knowledge_base AS kb ON kb.document_id = d.id
                WHERE d.project_id = $1
                GROUP BY
                    d.id,
                    d.file_name,
                    d.file_size,
                    d.status,
                    d.error,
                    d.uploaded_by,
                    d.created_at,
                    d.updated_at
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
                chunk_count=int(row["chunk_count"] or 0),
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
                SELECT id, project_id, file_name, file_size, status, error, uploaded_by, created_at, updated_at
                FROM knowledge_documents
                WHERE id = $1
            """,
                ensure_uuid(document_id),
            )

            if not row:
                return None

            chunk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM knowledge_base WHERE document_id = $1",
                row["id"],
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
            chunk_count=int(chunk_count or 0),
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

    async def delete_document_chunks(self, document_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM knowledge_base WHERE document_id = $1",
                ensure_uuid(document_id),
            )

    async def delete_document(self, document_id: str) -> None:
        logger.info("Deleting knowledge document", extra={"document_id": document_id})

        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM knowledge_base WHERE document_id = $1",
                ensure_uuid(document_id),
            )
            await conn.execute(
                "DELETE FROM knowledge_documents WHERE id = $1",
                ensure_uuid(document_id),
            )

        logger.info("Document deleted", extra={"document_id": document_id})

    async def clear_project_knowledge(self, project_id: str) -> None:
        logger.info("Clearing knowledge base", extra={"project_id": project_id})

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM knowledge_base WHERE project_id = $1",
                    ensure_uuid(project_id),
                )
                await conn.execute(
                    "DELETE FROM knowledge_documents WHERE project_id = $1",
                    ensure_uuid(project_id),
                )

        logger.info("Knowledge base cleared", extra={"project_id": project_id})
