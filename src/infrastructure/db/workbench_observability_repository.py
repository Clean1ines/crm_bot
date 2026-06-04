from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, cast


class WorkbenchObservabilityDbPool(Protocol):
    async def fetchrow(self, query: str, *args: object) -> object | None: ...

    async def fetch(self, query: str, *args: object) -> Sequence[object]: ...


class WorkbenchObservabilityRepository:
    def __init__(self, pool: WorkbenchObservabilityDbPool) -> None:
        self._pool = pool

    async def fetch_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        row = await self._pool.fetchrow(
            """
            SELECT
                document_id,
                project_id,
                file_name,
                status,
                created_at,
                updated_at
            FROM knowledge_workbench_documents
            WHERE project_id = $1 AND document_id = $2
              AND deleted_at IS NULL
            """,
            project_id,
            document_id,
        )
        return _row_to_dict(row)

    async def fetch_latest_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        row = await self._pool.fetchrow(
            """
            SELECT
                processing_run_id,
                status,
                trigger,
                processing_method,
                started_at,
                completed_at AS finished_at,
                created_at
            FROM knowledge_workbench_processing_runs
            WHERE project_id = $1 AND document_id = $2
            ORDER BY started_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """,
            project_id,
            document_id,
        )
        return _row_to_dict(row)

    async def fetch_section_status_counts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, int]:
        rows = await self._pool.fetch(
            """
            SELECT status, COUNT(*)::int AS count
            FROM knowledge_workbench_document_sections
            WHERE project_id = $1 AND document_id = $2
            GROUP BY status
            ORDER BY status
            """,
            project_id,
            document_id,
        )
        return {
            str(row["status"]): _int(row["count"])
            for row in (_row_to_dict(item) or {} for item in rows)
            if row
        }

    async def fetch_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[Mapping[str, object], ...]:
        rows = await self._pool.fetch(
            """
            SELECT
                node_run_id,
                node_name,
                node_kind,
                status,
                started_at,
                completed_at AS finished_at
            FROM knowledge_workbench_processing_node_runs
            WHERE project_id = $1
              AND document_id = $2
              AND processing_run_id = $3
            ORDER BY started_at ASC NULLS LAST, created_at ASC NULLS LAST
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        return tuple(row for item in rows if (row := _row_to_dict(item)) is not None)

    async def get_evidence_trace_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> dict[str, object] | None:
        row = await self._pool.fetchrow(
            """
            SELECT
                document_id,
                project_id,
                file_name,
                source_type,
                file_size_bytes,
                status,
                current_processing_run_id,
                created_at,
                updated_at,
                deleted_at
            FROM knowledge_workbench_documents
            WHERE project_id = $1 AND document_id = $2
              AND deleted_at IS NULL
            """,
            project_id,
            document_id,
        )
        if row is None:
            return None
        return _row_to_dict_required(row)

    async def list_evidence_trace_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                section_id,
                section_key,
                section_index,
                title,
                status,
                raw_text,
                normalized_text,
                source_refs,
                source_chunk_indexes,
                metadata,
                created_at,
                updated_at
            FROM knowledge_workbench_document_sections
            WHERE project_id = $1 AND document_id = $2
            ORDER BY section_index ASC, section_key ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_evidence_trace_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                artifact.artifact_id || ':' || (claim.ordinality - 1)::text
                    AS claim_observation_id,
                artifact.section_id,
                'claim_observation' AS action,
                node.status AS status,
                NULL::text AS target_fact_id,
                claim.item->>'local_ref' AS claim_local_ref,
                claim.item->>'claim' AS title,
                claim.item->>'claim' AS claim,
                COALESCE(claim.item->>'claim_kind', 'other') AS claim_kind,
                COALESCE(claim.item->>'scope', claim.item->>'claim') AS answer,
                claim.item->>'claim' AS short_answer,
                NULL::text AS claim_delta,
                COALESCE(claim.item->'possible_questions', '[]'::jsonb) AS variants,
                CASE
                    WHEN COALESCE(claim.item->>'evidence_block', '') = ''
                    THEN '[]'::jsonb
                    ELSE jsonb_build_array(claim.item->>'evidence_block')
                END AS evidence_quotes,
                COALESCE(claim.item->'source_refs', '[]'::jsonb) AS source_refs,
                COALESCE(claim.item->'source_chunk_indexes', '[]'::jsonb)
                    AS source_chunk_indexes,
                NULLIF(claim.item->>'confidence', '')::double precision AS confidence,
                COALESCE(claim.item->>'exclusion_scope', '') AS reason,
                artifact.created_at
            FROM knowledge_workbench_processing_node_artifacts AS artifact
            JOIN knowledge_workbench_processing_node_runs AS node
              ON node.node_run_id = artifact.node_run_id
             AND node.processing_run_id = artifact.processing_run_id
             AND node.project_id = artifact.project_id
             AND node.document_id = artifact.document_id
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(artifact.payload_json->'claim_observations', '[]'::jsonb)
            ) WITH ORDINALITY AS claim(item, ordinality)
            LEFT JOIN knowledge_workbench_document_sections AS section
              ON section.section_id = artifact.section_id
             AND section.document_id = artifact.document_id
             AND section.project_id = artifact.project_id
            WHERE artifact.project_id = $1
              AND artifact.document_id = $2
              AND node.node_name = 'faq_surface_claim_observations'
              AND artifact.artifact_type = 'parsed_llm_output'
            ORDER BY
                section.section_index NULLS LAST,
                artifact.created_at ASC,
                claim.ordinality ASC,
                artifact.artifact_id ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_evidence_trace_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                f.fact_id AS fact_id,
                f.fact_id AS fact_key,
                f.claim,
                f.possible_questions AS question_variants,
                f.claim_kind,
                COALESCE(NULLIF(f.scope, ''), f.claim) AS answer,
                f.claim AS short_answer,
                f.scope AS answer_scope,
                f.scope AS retrieval_scope,
                f.exclusion_scope,
                COALESCE(
                    jsonb_agg(DISTINCT m.evidence_block)
                        FILTER (WHERE m.evidence_block <> ''),
                    '[]'::jsonb
                ) AS evidence_quotes,
                COALESCE(
                    jsonb_agg(DISTINCT m.source_section_ref)
                        FILTER (WHERE m.source_section_ref <> ''),
                    '[]'::jsonb
                ) AS source_refs,
                COALESCE(
                    jsonb_agg(DISTINCT m.source_section_id)
                        FILTER (WHERE m.source_section_id IS NOT NULL),
                    '[]'::jsonb
                ) AS source_section_ids,
                '[]'::jsonb AS source_chunk_indexes,
                f.status,
                f.updated_at
            FROM knowledge_workbench_canonical_facts AS f
            LEFT JOIN knowledge_workbench_fact_mentions AS m
              ON m.fact_id = f.fact_id
             AND m.fact_registry_id = f.fact_registry_id
            WHERE f.project_id = $1
              AND f.document_id = $2
              AND f.status <> 'deleted'
            GROUP BY
                f.fact_id,
                f.claim,
                f.possible_questions,
                f.claim_kind,
                f.scope,
                f.exclusion_scope,
                f.status,
                f.updated_at
            ORDER BY f.fact_id ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_evidence_trace_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                surface_id,
                fact_id,
                title,
                claim,
                question_variants,
                answer,
                short_answer,
                answer_scope,
                retrieval_scope,
                exclusion_scope,
                evidence_quotes,
                source_refs,
                source_section_ids,
                claim_kind,
                status,
                curation_state,
                created_at,
                updated_at
            FROM knowledge_workbench_surfaces
            WHERE project_id = $1 AND document_id = $2
              AND status <> 'deleted'
            ORDER BY created_at ASC, surface_id ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_workbench_documents(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
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
                d.uploaded_by_user_id,
                d.uploaded_by_actor_type,
                d.uploaded_by_actor_id,
                d.trusted_upload,
                d.last_error_kind,
                d.last_error_message,
                d.last_error_at,
                d.created_at,
                d.updated_at,
                d.deleted_at,

                pr.processing_run_id,
                pr.status AS processing_status,
                pr.trigger AS processing_trigger,
                pr.resume_policy,
                pr.started_at,
                pr.completed_at AS finished_at,
                pr.completed_at,
                COALESCE(pr.active_elapsed_seconds, 0) AS active_elapsed_seconds,
                COALESCE(pr.wall_elapsed_seconds, 0) AS wall_elapsed_seconds,
                COALESCE(pr.total_prompt_tokens, 0) AS prompt_tokens,
                COALESCE(pr.total_completion_tokens, 0) AS completion_tokens,
                COALESCE(pr.total_tokens, 0) AS total_tokens,
                COALESCE(pr.total_llm_calls, 0) AS llm_call_count,
                pr.last_error_kind AS processing_last_error_kind,
                pr.last_error_report_id,
                pr.last_user_message AS processing_last_user_message,

                COALESCE(section_counts.total_sections, 0) AS section_count,
                COALESCE(section_counts.processed_sections, 0) AS processed_section_count,
                COALESCE(section_counts.failed_sections, 0) AS failed_section_count,
                COALESCE(section_counts.pending_sections, 0) AS pending_section_count,

                COALESCE(registry_summary.canonical_fact_count, 0) AS canonical_fact_count,
                registry_summary.final_registry_snapshot_id,
                COALESCE(registry_summary.registry_retained, FALSE) AS registry_retained,

                COALESCE(surface_summary.draft_count, 0) AS surface_draft_count,
                COALESCE(surface_summary.ready_count, 0) AS surface_ready_count,
                COALESCE(surface_summary.published_count, 0) AS surface_published_count,
                COALESCE(surface_summary.rejected_count, 0) AS surface_rejected_count,

                curation.curation_session_id,
                curation.status AS curation_session_status,

                runtime_summary.publication_id,
                COALESCE(runtime_summary.runtime_entry_count, 0) AS runtime_entry_count,

                auto_recovery.auto_resume_scheduled_at
            FROM knowledge_workbench_documents AS d
            LEFT JOIN LATERAL (

                SELECT

                    COUNT(f.fact_id)::int AS canonical_fact_count,

                    (

                        SELECT rs.snapshot_id

                        FROM knowledge_workbench_registry_snapshots AS rs

                        WHERE rs.project_id = d.project_id

                          AND rs.document_id = d.document_id

                          AND rs.is_final_published IS TRUE

                        ORDER BY

                            rs.sequence_number DESC,

                            rs.created_at DESC

                        LIMIT 1

                    ) AS final_registry_snapshot_id,

                    (

                        BOOL_OR(fr.retention_state = 'published_retained')

                        OR EXISTS (

                            SELECT 1

                            FROM knowledge_workbench_registry_snapshots AS rs

                            WHERE rs.project_id = d.project_id

                              AND rs.document_id = d.document_id

                              AND rs.is_final_published IS TRUE

                        )

                    ) AS registry_retained

                FROM knowledge_workbench_fact_registries AS fr

                LEFT JOIN knowledge_workbench_canonical_facts AS f

                  ON f.fact_registry_id = fr.fact_registry_id

                 AND f.project_id = fr.project_id

                 AND f.document_id = fr.document_id

                 AND f.status <> 'deleted'

                WHERE fr.project_id = d.project_id

                  AND fr.document_id = d.document_id

            ) AS registry_summary ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (
                        WHERE s.status IN ('draft', 'needs_review')
                    )::int AS draft_count,
                    COUNT(*) FILTER (
                        WHERE s.status IN ('ready', 'publish_ready')
                    )::int AS ready_count,
                    COUNT(*) FILTER (
                        WHERE s.status = 'published'
                    )::int AS published_count,
                    COUNT(*) FILTER (
                        WHERE s.status IN ('rejected', 'deleted')
                    )::int AS rejected_count
                FROM knowledge_workbench_surfaces AS s
                WHERE s.project_id = d.project_id
                  AND s.document_id = d.document_id
                  AND s.status <> 'deleted'
            ) AS surface_summary ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    cs.curation_session_id,
                    cs.status
                FROM knowledge_workbench_surface_curation_sessions AS cs
                WHERE cs.project_id = d.project_id
                  AND cs.document_id = d.document_id
                ORDER BY cs.updated_at DESC NULLS LAST, cs.created_at DESC
                LIMIT 1
            ) AS curation ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    latest_publication.publication_id,
                    COUNT(rte.runtime_entry_id)::int AS runtime_entry_count
                FROM knowledge_workbench_surfaces AS s
                JOIN knowledge_workbench_runtime_retrieval_entries AS rte
                  ON rte.surface_id = s.surface_id
                 AND rte.project_id = s.project_id
                 AND rte.status = 'published'
                 AND rte.visibility = 'runtime'
                LEFT JOIN LATERAL (
                    SELECT publication_id
                    FROM knowledge_workbench_runtime_publications AS rp
                    WHERE rp.project_id = d.project_id
                      AND rp.status = 'published'
                    ORDER BY rp.published_at DESC NULLS LAST, rp.created_at DESC
                    LIMIT 1
                ) AS latest_publication ON TRUE
                WHERE s.project_id = d.project_id
                  AND s.document_id = d.document_id
                  AND s.status = 'published'
                GROUP BY latest_publication.publication_id
            ) AS runtime_summary ON TRUE
            LEFT JOIN LATERAL (
                SELECT q.next_attempt_at AS auto_resume_scheduled_at
                FROM execution_queue AS q
                WHERE q.task_type = 'process_workbench_document'
                  AND q.payload::jsonb ->> 'project_id' = d.project_id::text
                  AND q.payload::jsonb ->> 'document_id' = d.document_id
                  AND q.status IN ('pending', 'queued', 'scheduled', 'retry')
                  AND q.next_attempt_at IS NOT NULL
                ORDER BY q.next_attempt_at ASC
                LIMIT 1
            ) AS auto_recovery ON TRUE
            WHERE d.project_id = $1
              AND d.deleted_at IS NULL
            ORDER BY d.created_at DESC NULLS LAST, d.document_id DESC
            LIMIT $2 OFFSET $3
            """,
            project_id,
            limit,
            offset,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def get_import_quality_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> dict[str, object] | None:
        row = await self._pool.fetchrow(
            """
            SELECT
                document_id,
                project_id,
                file_name,
                source_type,
                file_size_bytes,
                status,
                current_processing_run_id,
                created_at,
                updated_at,
                deleted_at
            FROM knowledge_workbench_documents
            WHERE project_id = $1
              AND document_id = $2
              AND deleted_at IS NULL
            """,
            project_id,
            document_id,
        )
        if row is None:
            return None
        return _row_to_dict_required(row)

    async def list_import_quality_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                section_id,
                section_key,
                section_index,
                title,
                status,
                source_refs,
                source_chunk_indexes
            FROM knowledge_workbench_document_sections
            WHERE project_id = $1
              AND document_id = $2
            ORDER BY section_index ASC, section_key ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_import_quality_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        return []

    async def list_import_quality_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                f.fact_id AS fact_id,
                f.fact_id AS fact_key,
                f.status,
                COALESCE(
                    jsonb_agg(DISTINCT m.evidence_block)
                        FILTER (WHERE m.evidence_block <> ''),
                    '[]'::jsonb
                ) AS evidence_quotes,
                COALESCE(
                    jsonb_agg(DISTINCT m.source_section_ref)
                        FILTER (WHERE m.source_section_ref <> ''),
                    '[]'::jsonb
                ) AS source_refs,
                COALESCE(
                    jsonb_agg(DISTINCT m.source_section_id)
                        FILTER (WHERE m.source_section_id IS NOT NULL),
                    '[]'::jsonb
                ) AS source_section_ids,
                '[]'::jsonb AS source_chunk_indexes
            FROM knowledge_workbench_canonical_facts AS f
            LEFT JOIN knowledge_workbench_fact_mentions AS m
              ON m.fact_id = f.fact_id
             AND m.fact_registry_id = f.fact_registry_id
            WHERE f.project_id = $1
              AND f.document_id = $2
              AND f.status <> 'deleted'
            GROUP BY f.fact_id, f.status
            ORDER BY f.fact_id ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_import_quality_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                surface_id,
                fact_id,
                status,
                curation_state,
                evidence_quotes,
                source_refs,
                source_section_ids
            FROM knowledge_workbench_surfaces
            WHERE project_id = $1
              AND document_id = $2
              AND status <> 'deleted'
            ORDER BY created_at ASC, surface_id ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_import_quality_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                node_run_id,
                processing_run_id,
                node_name,
                status,
                error_kind,
                error_message,
                started_at,
                completed_at
            FROM knowledge_workbench_processing_node_runs
            WHERE project_id = $1
              AND document_id = $2
            ORDER BY started_at ASC NULLS LAST, node_run_id ASC
            """,
            project_id,
            document_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_processing_overview_documents(
        self,
        *,
        project_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                d.document_id,
                d.project_id,
                d.file_name,
                d.source_type,
                d.file_size_bytes,
                d.status,
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
                COALESCE(section_counts.total_sections, 0) AS section_count,
                COALESCE(section_counts.processed_sections, 0) AS processed_section_count,
                COALESCE(section_counts.failed_sections, 0) AS failed_section_count,
                COALESCE(section_counts.pending_sections, 0) AS pending_section_count
            FROM knowledge_workbench_documents AS d
            LEFT JOIN LATERAL (
                SELECT
                    r.processing_run_id,
                    r.status,
                    r.trigger,
                    r.resume_policy,
                    r.started_at,
                    r.completed_at,
                    r.created_at
                FROM knowledge_workbench_processing_runs AS r
                WHERE r.project_id = d.project_id
                  AND r.document_id = d.document_id
                ORDER BY r.started_at DESC NULLS LAST, r.created_at DESC NULLS LAST
                LIMIT 1
            ) AS pr ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*)::int AS total_sections,
                    COUNT(*) FILTER (
                        WHERE s.status IN ('processed', 'completed', 'materialized')
                    )::int AS processed_sections,
                    COUNT(*) FILTER (
                        WHERE s.status IN ('failed', 'error')
                    )::int AS failed_sections,
                    COUNT(*) FILTER (
                        WHERE s.status NOT IN (
                            'processed',
                            'completed',
                            'materialized',
                            'failed',
                            'error'
                        )
                    )::int AS pending_sections
                FROM knowledge_workbench_document_sections AS s
                WHERE s.project_id = d.project_id
                  AND s.document_id = d.document_id
            ) AS section_counts ON TRUE
            WHERE d.project_id = $1
              AND d.deleted_at IS NULL
            ORDER BY d.created_at DESC NULLS LAST, d.document_id DESC
            """,
            project_id,
        )
        return [_row_to_dict_required(row) for row in rows]

    async def list_processing_overview_node_runs(
        self,
        *,
        project_id: str,
    ) -> list[dict[str, object]]:
        rows = await self._pool.fetch(
            """
            SELECT
                node_run_id,
                project_id,
                document_id,
                processing_run_id,
                node_name,
                status,
                error_kind,
                error_message,
                started_at,
                completed_at
            FROM knowledge_workbench_processing_node_runs
            WHERE project_id = $1
            ORDER BY started_at DESC NULLS LAST, node_run_id DESC
            """,
            project_id,
        )
        return [_row_to_dict_required(row) for row in rows]


def _row_to_dict(row: object | None) -> dict[str, object] | None:
    if row is None:
        return None
    return _row_to_dict_required(row)


def _row_to_dict_required(row: object) -> dict[str, object]:
    return dict(cast(Mapping[str, object], row))


def _int(value: object) -> int:
    return int(str(value))
