from __future__ import annotations

import json

import asyncpg

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.utils.uuid_utils import ensure_uuid

PROCESSING_CANCELLED_REASON = "Остановлено пользователем"


async def create_document(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    file_name: str,
    file_size: int | None = None,
    uploaded_by: str | None = None,
) -> str:
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
    return str(row["id"])


async def update_document_status(
    conn: asyncpg.Connection,
    *,
    document_id: str,
    status: str,
    error: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_documents
        SET status = $1, error = $2, updated_at = NOW()
        WHERE id = $3
          AND NOT (
              $1 = 'processed'
              AND preprocessing_status = 'failed'
              AND preprocessing_error = $4
          )
        """,
        status,
        error,
        ensure_uuid(document_id),
        PROCESSING_CANCELLED_REASON,
    )


async def update_document_preprocessing_status(
    conn: asyncpg.Connection,
    *,
    document_id: str,
    mode: KnowledgePreprocessingMode,
    status: str,
    error: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    metrics: JsonObject | None = None,
) -> None:
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
          AND NOT (
              $2 = 'completed'
              AND preprocessing_status = 'failed'
              AND preprocessing_error = $8
          )
        """,
        mode,
        status,
        error,
        model,
        prompt_version,
        json.dumps(metrics, ensure_ascii=False) if metrics is not None else None,
        ensure_uuid(document_id),
        PROCESSING_CANCELLED_REASON,
    )


async def mark_document_processing_cancelled(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    reason: str,
) -> bool:
    row = await conn.fetchrow(
        """
        UPDATE knowledge_documents
        SET
            status = 'error',
            error = $3,
            preprocessing_status = 'failed',
            preprocessing_error = $3,
            updated_at = now()
        WHERE project_id = $1
          AND id = $2
        RETURNING id
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        reason,
    )
    return row is not None


async def merge_document_preprocessing_metrics(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    metrics: JsonObject,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_documents
        SET preprocessing_metrics = COALESCE(preprocessing_metrics, '{}'::jsonb)
            || $3::jsonb,
            updated_at = now()
        WHERE project_id = $1
          AND id = $2
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        json.dumps(metrics, ensure_ascii=False),
    )
