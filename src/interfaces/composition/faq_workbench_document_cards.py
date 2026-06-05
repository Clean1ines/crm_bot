from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_observability.document_cards import (
    WorkbenchDocumentListReadService,
)


class WorkbenchDocumentCardsDbPool(Protocol):
    async def acquire(self): ...


class WorkbenchDocumentCardsQuery:
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def list_workbench_documents(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        rows = await self._connection.fetch(
            """
            SELECT
                d.document_id,
                d.project_id,
                d.file_name,
                d.source_type,
                d.file_size_bytes,
                d.status,
                d.retention_state,
                d.current_processing_run_id,
                d.last_error_kind,
                d.last_error_message,
                d.last_error_at,
                d.created_at,
                d.updated_at,
                pr.processing_run_id,
                pr.status AS processing_status,
                pr.trigger AS processing_trigger,
                pr.resume_policy,
                pr.started_at,
                pr.completed_at,
                COALESCE(pr.active_elapsed_seconds, 0) AS active_elapsed_seconds,
                COALESCE(pr.wall_elapsed_seconds, 0) AS wall_elapsed_seconds,
                COALESCE(pr.total_prompt_tokens, 0) AS prompt_tokens,
                COALESCE(pr.total_completion_tokens, 0) AS completion_tokens,
                COALESCE(pr.total_tokens, 0) AS total_tokens,
                COALESCE(pr.total_llm_calls, 0) AS llm_call_count,
                pr.last_error_kind AS processing_last_error_kind,
                pr.last_user_message AS processing_last_user_message,
                COALESCE(section_counts.total_sections, 0) AS section_count,
                COALESCE(section_counts.processed_sections, 0) AS processed_section_count,
                COALESCE(section_counts.failed_sections, 0) AS failed_section_count,
                COALESCE(section_counts.pending_sections, 0) AS pending_section_count,
                COALESCE(registry_summary.canonical_fact_count, 0) AS canonical_fact_count,
                registry_summary.final_registry_snapshot_id,
                COALESCE(runtime_summary.runtime_entry_count, 0) AS runtime_entry_count,
                NULL::text AS publication_id
            FROM knowledge_workbench_documents AS d
            LEFT JOIN knowledge_workbench_processing_runs AS pr
              ON pr.project_id = d.project_id
             AND pr.document_id = d.document_id
             AND pr.processing_run_id = d.current_processing_run_id
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*)::int AS total_sections,
                    COUNT(*) FILTER (WHERE s.status IN ('processed', 'completed'))::int AS processed_sections,
                    COUNT(*) FILTER (WHERE s.status IN ('failed', 'error'))::int AS failed_sections,
                    COUNT(*) FILTER (WHERE s.status NOT IN ('processed', 'completed', 'failed', 'error'))::int AS pending_sections
                FROM knowledge_workbench_document_sections AS s
                WHERE s.project_id = d.project_id
                  AND s.document_id = d.document_id
            ) AS section_counts ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(f.fact_id)::int AS canonical_fact_count,
                    (
                        SELECT rs.snapshot_id
                        FROM knowledge_workbench_registry_snapshots AS rs
                        WHERE rs.project_id = d.project_id
                          AND rs.document_id = d.document_id
                          AND rs.is_final_published IS TRUE
                        ORDER BY rs.sequence_number DESC, rs.created_at DESC
                        LIMIT 1
                    ) AS final_registry_snapshot_id
                FROM knowledge_workbench_fact_registries AS fr
                LEFT JOIN knowledge_workbench_canonical_facts AS f
                  ON f.registry_id = fr.registry_id
                 AND f.project_id = fr.project_id
                 AND f.document_id = fr.document_id
                 AND f.status <> 'deleted'
                WHERE fr.project_id = d.project_id
                  AND fr.document_id = d.document_id
            ) AS registry_summary ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS runtime_entry_count
                FROM knowledge_workbench_runtime_retrieval_entries AS rte
                WHERE rte.project_id = d.project_id
                  AND rte.status = 'published'
                  AND rte.visibility = 'runtime'
                  AND EXISTS (
                      SELECT 1
                      FROM knowledge_workbench_canonical_facts AS f
                      WHERE f.project_id = d.project_id
                        AND f.document_id = d.document_id
                        AND f.fact_id = rte.fact_id
                        AND f.status <> 'deleted'
                  )
            ) AS runtime_summary ON TRUE
            WHERE d.project_id = $1
              AND d.deleted_at IS NULL
            ORDER BY d.created_at DESC NULLS LAST, d.document_id DESC
            LIMIT $2 OFFSET $3
            """,
            project_id,
            limit,
            offset,
        )
        return [dict(row) for row in rows]


async def list_workbench_document_cards(
    *,
    pool: WorkbenchDocumentCardsDbPool,
    project_id: str,
    limit: int,
    offset: int,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        service = WorkbenchDocumentListReadService(
            WorkbenchDocumentCardsQuery(connection)
        )
        return await service.list_documents(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["list_workbench_document_cards"]
