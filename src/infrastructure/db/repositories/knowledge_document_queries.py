from __future__ import annotations

import asyncpg

from src.domain.project_plane.knowledge_views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentView,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import normalize_timestamp
from src.utils.uuid_utils import ensure_uuid


async def list_project_documents(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[KnowledgeDocumentView]:
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
            COUNT(DISTINCT rs.entry_id)::int AS runtime_entry_count,
            COALESCE(mu.llm_tokens_input, 0)::bigint AS llm_tokens_input,
            COALESCE(mu.llm_tokens_output, 0)::bigint AS llm_tokens_output,
            COALESCE(mu.llm_tokens_total, 0)::bigint AS llm_tokens_total,
            COALESCE(mu.llm_usage_events_count, 0)::int AS llm_usage_events_count,
            COALESCE(mu.llm_models, '') AS llm_models
        FROM knowledge_documents AS d
        LEFT JOIN knowledge_entries AS ke ON ke.document_id = d.id
        LEFT JOIN knowledge_retrieval_surface AS rs ON rs.entry_id = ke.id
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
            d.preprocessing_metrics,
            mu.llm_tokens_input,
            mu.llm_tokens_output,
            mu.llm_tokens_total,
            mu.llm_usage_events_count,
            mu.llm_models
        ORDER BY d.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        ensure_uuid(project_id),
        limit,
        offset,
    )

    return [
        KnowledgeDocumentView(
            id=str(row["id"]),
            file_name=str(row["file_name"]),
            file_size=int(row["file_size"]) if row["file_size"] is not None else None,
            status=str(row["status"]),
            error=str(row["error"]) if row["error"] is not None else None,
            uploaded_by=str(row["uploaded_by"])
            if row["uploaded_by"] is not None
            else None,
            created_at=normalize_timestamp(row["created_at"]),
            updated_at=normalize_timestamp(row["updated_at"]),
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
            llm_tokens_input=int(row["llm_tokens_input"] or 0),
            llm_tokens_output=int(row["llm_tokens_output"] or 0),
            llm_tokens_total=int(row["llm_tokens_total"] or 0),
            llm_usage_events_count=int(row["llm_usage_events_count"] or 0),
            llm_models=str(row["llm_models"] or ""),
        )
        for row in rows or []
    ]


async def get_document_detail(
    conn: asyncpg.Connection,
    *,
    document_id: str,
) -> KnowledgeDocumentDetailView | None:
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
    runtime_entry_count = int(counts["runtime_entry_count"] or 0) if counts else 0

    return KnowledgeDocumentDetailView(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        file_name=str(row["file_name"]),
        file_size=int(row["file_size"]) if row["file_size"] is not None else None,
        status=str(row["status"]),
        error=str(row["error"]) if row["error"] is not None else None,
        uploaded_by=str(row["uploaded_by"]) if row["uploaded_by"] is not None else None,
        created_at=normalize_timestamp(row["created_at"]),
        updated_at=normalize_timestamp(row["updated_at"]),
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
