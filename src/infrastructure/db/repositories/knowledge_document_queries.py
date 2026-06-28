from __future__ import annotations

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import normalize_timestamp
from src.utils.uuid_utils import ensure_uuid


WORKBENCH_DOCUMENT_COUNTERS_SQL = """
WITH source_unit_counts AS (
    SELECT
        source_doc.document_ref,
        COUNT(DISTINCT source_unit.unit_ref)::int AS source_unit_count
    FROM source_documents AS source_doc
    LEFT JOIN source_units AS source_unit
      ON source_unit.document_ref = source_doc.document_ref
    GROUP BY source_doc.document_ref
),
draft_claim_counts AS (
    SELECT
        source_unit.document_ref,
        COUNT(DISTINCT observation.observation_ref)::int AS draft_claim_count
    FROM source_units AS source_unit
    LEFT JOIN draft_claim_observations AS observation
      ON observation.source_unit_ref = source_unit.unit_ref
    GROUP BY source_unit.document_ref
),
draft_claim_embedding_counts AS (
    SELECT
        embedding.source_document_ref AS document_ref,
        COUNT(DISTINCT embedding.embedding_ref)::int AS draft_claim_embedding_count
    FROM draft_claim_embeddings AS embedding
    GROUP BY embedding.source_document_ref
),
curation_counts AS (
    SELECT
        workspace.source_document_ref AS document_ref,
        COUNT(DISTINCT item.item_ref)::int AS curated_item_count
    FROM draft_claim_curation_workspaces AS workspace
    LEFT JOIN draft_claim_curation_items AS item
      ON item.workspace_ref = workspace.workspace_ref
     AND item.excluded = FALSE
    GROUP BY workspace.source_document_ref
),
runtime_entry_counts AS (
    SELECT
        entry.source_refs->>'source_document_ref' AS document_ref,
        COUNT(DISTINCT entry.runtime_entry_id)::int AS runtime_entry_count
    FROM knowledge_workbench_runtime_retrieval_entries AS entry
    WHERE entry.visibility = 'published'
      AND entry.status = 'active'
    GROUP BY entry.source_refs->>'source_document_ref'
),
runtime_embedding_counts AS (
    SELECT
        entry.source_refs->>'source_document_ref' AS document_ref,
        COUNT(DISTINCT embedding.runtime_entry_id || ':' || embedding.embedding_model_id || ':' || embedding.embedding_text_hash)::int
            AS runtime_embedding_count
    FROM knowledge_workbench_runtime_retrieval_entries AS entry
    JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS embedding
      ON embedding.runtime_entry_id = entry.runtime_entry_id
    WHERE entry.visibility = 'published'
      AND entry.status = 'active'
    GROUP BY entry.source_refs->>'source_document_ref'
),
publication_counts AS (
    SELECT
        entry.source_refs->>'source_document_ref' AS document_ref,
        COUNT(DISTINCT publication.publication_id)::int AS publication_count
    FROM knowledge_workbench_runtime_retrieval_entries AS entry
    JOIN knowledge_workbench_runtime_publications AS publication
      ON publication.project_id = entry.project_id
    WHERE entry.visibility = 'published'
      AND entry.status = 'active'
      AND publication.status = 'published'
    GROUP BY entry.source_refs->>'source_document_ref'
)
SELECT
    COALESCE(source_unit_counts.source_unit_count, 0)::int AS source_unit_count,
    COALESCE(draft_claim_counts.draft_claim_count, 0)::int AS draft_claim_count,
    COALESCE(draft_claim_embedding_counts.draft_claim_embedding_count, 0)::int AS draft_claim_embedding_count,
    COALESCE(curation_counts.curated_item_count, 0)::int AS curated_item_count,
    COALESCE(runtime_entry_counts.runtime_entry_count, 0)::int AS runtime_entry_count,
    COALESCE(runtime_embedding_counts.runtime_embedding_count, 0)::int AS runtime_embedding_count,
    COALESCE(publication_counts.publication_count, 0)::int AS publication_count
"""


async def list_project_documents(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[KnowledgeDocumentView]:
    rows = await conn.fetch(
        f"""
        {WORKBENCH_DOCUMENT_COUNTERS_SQL},
        documents AS (
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
                COALESCE(mu.llm_tokens_input, 0)::bigint AS llm_tokens_input,
                COALESCE(mu.llm_tokens_output, 0)::bigint AS llm_tokens_output,
                COALESCE(mu.llm_tokens_total, 0)::bigint AS llm_tokens_total,
                COALESCE(mu.llm_usage_events_count, 0)::int AS llm_usage_events_count,
                COALESCE(mu.llm_models, '') AS llm_models
            FROM knowledge_documents AS d
            LEFT JOIN (
                SELECT
                    document_id,
                    COALESCE(SUM(tokens_input), 0)::bigint AS llm_tokens_input,
                    COALESCE(SUM(tokens_output), 0)::bigint AS llm_tokens_output,
                    COALESCE(SUM(tokens_total), 0)::bigint AS llm_tokens_total,
                    COUNT(*)::int AS llm_usage_events_count,
                    STRING_AGG(
                        DISTINCT provider || ': ' || model,
                        ', ' ORDER BY provider || ': ' || model
                    ) AS llm_models
                FROM model_usage_events
                WHERE usage_type = 'llm'
                  AND document_id IS NOT NULL
                GROUP BY document_id
            ) AS mu ON mu.document_id = d.id
            WHERE d.project_id = $1
            ORDER BY d.created_at DESC
            LIMIT $2::int OFFSET $3
        )
        SELECT
            documents.*,
            counters.source_unit_count,
            counters.draft_claim_count,
            counters.draft_claim_embedding_count,
            counters.curated_item_count,
            counters.runtime_entry_count,
            counters.runtime_embedding_count,
            counters.publication_count
        FROM documents
        LEFT JOIN counters
          ON counters.document_ref = documents.id::text
        ORDER BY documents.created_at DESC
        """,
        ensure_uuid(project_id),
        limit,
        offset,
    )

    return [_document_view_from_row(row) for row in rows or []]


async def get_document_detail(
    conn: asyncpg.Connection,
    *,
    document_id: str,
) -> KnowledgeDocumentDetailView | None:
    row = await conn.fetchrow(
        f"""
        {WORKBENCH_DOCUMENT_COUNTERS_SQL},
        document AS (
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
        )
        SELECT
            document.*,
            counters.source_unit_count,
            counters.draft_claim_count,
            counters.draft_claim_embedding_count,
            counters.curated_item_count,
            counters.runtime_entry_count,
            counters.runtime_embedding_count,
            counters.publication_count
        FROM document
        LEFT JOIN counters
          ON counters.document_ref = document.id::text
        """,
        ensure_uuid(document_id),
    )

    if not row:
        return None

    return _document_detail_view_from_row(row)


def _row_int(row: asyncpg.Record, key: str) -> int:
    value = row[key]
    return int(value or 0)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _document_view_from_row(row: asyncpg.Record) -> KnowledgeDocumentView:
    source_unit_count = _row_int(row, "source_unit_count")
    runtime_entry_count = _row_int(row, "runtime_entry_count")
    runtime_embedding_count = _row_int(row, "runtime_embedding_count")

    return KnowledgeDocumentView(
        id=str(row["id"]),
        file_name=str(row["file_name"]),
        file_size=int(row["file_size"]) if row["file_size"] is not None else None,
        status=str(row["status"]),
        error=_optional_text(row["error"]),
        uploaded_by=_optional_text(row["uploaded_by"]),
        created_at=normalize_timestamp(row["created_at"]),
        updated_at=normalize_timestamp(row["updated_at"]),
        preprocessing_mode=_optional_text(row["preprocessing_mode"]),
        preprocessing_status=_optional_text(row["preprocessing_status"]),
        preprocessing_error=_optional_text(row["preprocessing_error"]),
        preprocessing_model=_optional_text(row["preprocessing_model"]),
        preprocessing_prompt_version=_optional_text(
            row["preprocessing_prompt_version"]
        ),
        preprocessing_metrics=row["preprocessing_metrics"],
        source_unit_count=source_unit_count,
        draft_claim_count=_row_int(row, "draft_claim_count"),
        draft_claim_embedding_count=_row_int(row, "draft_claim_embedding_count"),
        curated_item_count=_row_int(row, "curated_item_count"),
        runtime_entry_count=runtime_entry_count,
        runtime_embedding_count=runtime_embedding_count,
        publication_count=_row_int(row, "publication_count"),
        llm_tokens_input=_row_int(row, "llm_tokens_input"),
        llm_tokens_output=_row_int(row, "llm_tokens_output"),
        llm_tokens_total=_row_int(row, "llm_tokens_total"),
        llm_usage_events_count=_row_int(row, "llm_usage_events_count"),
        llm_models=str(row["llm_models"] or ""),
    )


def _document_detail_view_from_row(row: asyncpg.Record) -> KnowledgeDocumentDetailView:
    source_unit_count = _row_int(row, "source_unit_count")
    runtime_entry_count = _row_int(row, "runtime_entry_count")
    runtime_embedding_count = _row_int(row, "runtime_embedding_count")

    return KnowledgeDocumentDetailView(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        file_name=str(row["file_name"]),
        file_size=int(row["file_size"]) if row["file_size"] is not None else None,
        status=str(row["status"]),
        error=_optional_text(row["error"]),
        uploaded_by=_optional_text(row["uploaded_by"]),
        created_at=normalize_timestamp(row["created_at"]),
        updated_at=normalize_timestamp(row["updated_at"]),
        preprocessing_mode=_optional_text(row["preprocessing_mode"]),
        preprocessing_status=_optional_text(row["preprocessing_status"]),
        preprocessing_error=_optional_text(row["preprocessing_error"]),
        preprocessing_model=_optional_text(row["preprocessing_model"]),
        preprocessing_prompt_version=_optional_text(
            row["preprocessing_prompt_version"]
        ),
        preprocessing_metrics=row["preprocessing_metrics"],
        source_unit_count=source_unit_count,
        draft_claim_count=_row_int(row, "draft_claim_count"),
        draft_claim_embedding_count=_row_int(row, "draft_claim_embedding_count"),
        curated_item_count=_row_int(row, "curated_item_count"),
        runtime_entry_count=runtime_entry_count,
        runtime_embedding_count=runtime_embedding_count,
        publication_count=_row_int(row, "publication_count"),
    )


async def is_document_processing_cancelled(
    conn: asyncpg.Connection,
    *,
    document_id: str,
) -> bool:
    row = await conn.fetchrow(
        """
        SELECT status, preprocessing_status
        FROM knowledge_documents
        WHERE id = $1
        """,
        ensure_uuid(document_id),
    )

    if row is None:
        return True

    status = str(row["status"] or "")
    preprocessing_status = str(row["preprocessing_status"] or "")
    return status == "error" or preprocessing_status in {"failed", "cancelled"}
