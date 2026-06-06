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
                pr.current_active_started_at AS current_active_started_at,
                COALESCE(pr.total_prompt_tokens, 0) AS prompt_tokens,
                COALESCE(pr.total_completion_tokens, 0) AS completion_tokens,
                COALESCE(pr.total_tokens, 0) AS total_tokens,
                COALESCE(pr.total_llm_calls, 0) AS llm_call_count,
                pr.last_error_kind AS processing_last_error_kind,
                pr.last_user_message AS processing_last_user_message,
                COALESCE(section_counts.total_sections, 0) AS section_count,
                COALESCE(
                    section_queue_stats.prompt_a_done_count,
                    section_counts.processed_sections,
                    0
                ) AS processed_section_count,
                COALESCE(
                    section_queue_stats.failed_count,
                    section_counts.failed_sections,
                    0
                ) AS failed_section_count,
                GREATEST(
                    COALESCE(section_counts.total_sections, 0)
                    - COALESCE(section_queue_stats.prompt_a_done_count, 0)
                    - COALESCE(section_queue_stats.failed_count, 0),
                    0
                ) AS pending_section_count,

                COALESCE(section_queue_stats.ready_count, 0) AS section_queue_ready_count,
                COALESCE(section_queue_stats.leased_count, 0) AS section_queue_leased_count,
                COALESCE(section_queue_stats.prompt_a_done_count, 0) AS prompt_a_completed_sections,
                COALESCE(section_queue_stats.registry_application_queued_count, 0) AS section_queue_registry_application_queued_count,
                COALESCE(section_queue_stats.registry_application_applied_count, 0) AS section_queue_registry_application_applied_count,
                COALESCE(section_queue_stats.waiting_for_fresh_registry_count, 0) AS section_queue_waiting_for_fresh_registry_count,
                COALESCE(section_queue_stats.failed_count, 0) AS section_queue_failed_count,
                COALESCE(section_queue_stats.total_attempt_count, 0) AS section_queue_total_attempt_count,
                COALESCE(section_queue_stats.max_attempt_count, 0) AS section_queue_max_attempt_count,

                0::int AS registry_application_ready_count,
                0::int AS registry_application_leased_count,
                0::int AS registry_application_waiting_for_fresh_registry_count,
                0::int AS registry_application_applied_count,
                0::int AS registry_application_failed_count,

                0::int AS embedding_indexed_claims,
                0::int AS embedding_indexed_node_runs,

                COALESCE(local_claim_preview.claim_preview, '[]'::jsonb) AS workbench_claim_preview,
                COALESCE(local_claim_preview.claim_count, 0) AS workbench_claim_preview_count,

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
                    COUNT(*) FILTER (WHERE q.status = 'ready')::int AS ready_count,
                    COUNT(*) FILTER (WHERE q.status = 'leased')::int AS leased_count,
                    COUNT(*) FILTER (
                        WHERE q.status IN (
                            'claim_observations_persisted',
                            'registry_application_queued',
                            'registry_application_applied',
                            'waiting_for_fresh_registry'
                        )
                    )::int AS prompt_a_done_count,
                    COUNT(*) FILTER (WHERE q.status = 'registry_application_queued')::int AS registry_application_queued_count,
                    COUNT(*) FILTER (WHERE q.status = 'registry_application_applied')::int AS registry_application_applied_count,
                    COUNT(*) FILTER (WHERE q.status = 'waiting_for_fresh_registry')::int AS waiting_for_fresh_registry_count,
                    COUNT(*) FILTER (WHERE q.status = 'failed')::int AS failed_count,
                    COALESCE(SUM(q.attempt_count), 0)::int AS total_attempt_count,
                    COALESCE(MAX(q.attempt_count), 0)::int AS max_attempt_count
                FROM knowledge_workbench_section_batch_queue_items AS q
                WHERE q.project_id = d.project_id
                  AND q.document_id = d.document_id
                  AND (
                    d.current_processing_run_id IS NULL
                    OR q.processing_run_id = d.current_processing_run_id
                  )
            ) AS section_queue_stats ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*)::int AS claim_count,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'claim_id', claim_rows.claim_id,
                                'node_run_id', claim_rows.node_run_id,
                                'section_id', claim_rows.section_id,
                                'section_index', claim_rows.section_index,
                                'section_title', claim_rows.section_title,
                                'local_ref', COALESCE(claim_rows.claim_json ->> 'local_ref', claim_rows.claim_json ->> 'id', claim_rows.claim_json ->> 'claim_id'),
                                'claim', COALESCE(claim_rows.claim_json ->> 'claim', claim_rows.claim_json ->> 'canonical_claim', claim_rows.claim_json ->> 'canonical_formulation', claim_rows.claim_json ->> 'canonical_statement', claim_rows.claim_json ->> 'text'),
                                'claim_kind', COALESCE(claim_rows.claim_json ->> 'claim_kind', claim_rows.claim_json ->> 'claim_type', claim_rows.claim_json ->> 'type'),
                                'granularity', claim_rows.claim_json ->> 'granularity',
                                'evidence_block', COALESCE(claim_rows.claim_json ->> 'evidence_block', claim_rows.claim_json ->> 'evidence', claim_rows.claim_json ->> 'quote'),
                                'scope', claim_rows.claim_json ->> 'scope',
                                'exclusion_scope', claim_rows.claim_json ->> 'exclusion_scope',
                                'possible_questions', COALESCE(claim_rows.claim_json -> 'possible_questions', '[]'::jsonb),
                                'triples', COALESCE(claim_rows.claim_json -> 'triples', claim_rows.claim_json -> 'rdf_triples', '[]'::jsonb),
                                'local_relations', COALESCE(claim_rows.claim_json -> 'local_relations', claim_rows.claim_json -> 'relations', '[]'::jsonb),
                                'confidence', claim_rows.claim_json -> 'confidence'
                            )
                            ORDER BY claim_rows.section_index, claim_rows.ordinality
                        ),
                        '[]'::jsonb
                    ) AS claim_preview
                FROM (
                    SELECT
                        a.node_run_id,
                        a.section_id,
                        s.section_index,
                        s.title AS section_title,
                        claim_items.claim_json,
                        claim_items.ordinality,
                        a.node_run_id || ':' || claim_items.ordinality::text AS claim_id
                    FROM knowledge_workbench_processing_node_artifacts AS a
                    LEFT JOIN knowledge_workbench_document_sections AS s
                      ON s.project_id = a.project_id
                     AND s.document_id = a.document_id
                     AND s.section_id = a.section_id
                    CROSS JOIN LATERAL jsonb_array_elements(
                        COALESCE(a.payload_json -> 'claim_observations', '[]'::jsonb)
                    ) WITH ORDINALITY AS claim_items(claim_json, ordinality)
                    WHERE a.project_id = d.project_id
                      AND a.document_id = d.document_id
                      AND (
                        d.current_processing_run_id IS NULL
                        OR a.processing_run_id = d.current_processing_run_id
                      )
                      AND a.payload_json ? 'claim_observations'
                    ORDER BY s.section_index NULLS LAST, claim_items.ordinality
                    LIMIT 20
                ) AS claim_rows
            ) AS local_claim_preview ON TRUE
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
