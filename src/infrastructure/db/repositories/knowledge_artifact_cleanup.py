from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol, TypeAlias, TypeGuard, cast

from src.domain.project_plane.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupCounters,
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
)

CANCELLABLE_KNOWLEDGE_JOB_TYPES: tuple[str, ...] = (
    "process_knowledge_upload",
    "run_full_rag_eval",
)

TERMINAL_QUEUE_STATUSES: tuple[str, ...] = (
    "completed",
    "failed",
    "cancelled",
    "succeeded",
    "done",
)

CLEANUP_QUEUE_STATUS = "cancelled"
CLEANUP_QUEUE_ERROR = "Knowledge artifact cleanup cancelled queued work"


class TransactionContext(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...


class ConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    def transaction(self) -> TransactionContext: ...


class AcquireContext(Protocol):
    async def __aenter__(self) -> ConnectionLike: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...


class PoolLike(Protocol):
    def acquire(self) -> AcquireContext: ...


ConnectionOrPool: TypeAlias = ConnectionLike | PoolLike


def _is_connection(value: ConnectionOrPool) -> TypeGuard[ConnectionLike]:
    return hasattr(value, "execute") and hasattr(value, "transaction")


@asynccontextmanager
async def _acquire_connection(
    target: ConnectionOrPool,
) -> AsyncIterator[ConnectionLike]:
    if _is_connection(target):
        yield target
        return

    pool = cast(PoolLike, target)
    async with pool.acquire() as conn:
        yield conn


def _affected_count(status: str) -> int:
    tail = status.rsplit(" ", maxsplit=1)[-1]
    return int(tail) if tail.isdigit() else 0


async def _execute_count(
    conn: ConnectionLike,
    query: str,
    *args: object,
) -> int:
    return _affected_count(await conn.execute(query, *args))


async def _cancel_document_queue_jobs(
    conn: ConnectionLike,
    *,
    document_id: str,
) -> int:
    return await _execute_count(
        conn,
        """
        UPDATE execution_queue
        SET
            status = $4,
            attempts = max_attempts,
            error = $5,
            locked_at = NULL,
            worker_id = NULL,
            next_attempt_at = NULL,
            updated_at = now()
        WHERE payload::jsonb ->> 'document_id' = $1
          AND task_type = ANY($2::text[])
          AND NOT (status = ANY($3::text[]))
        """,
        document_id,
        list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
        list(TERMINAL_QUEUE_STATUSES),
        CLEANUP_QUEUE_STATUS,
        CLEANUP_QUEUE_ERROR,
    )


async def _cancel_project_queue_jobs(
    conn: ConnectionLike,
    *,
    project_id: str,
) -> int:
    return await _execute_count(
        conn,
        """
        UPDATE execution_queue
        SET
            status = $4,
            attempts = max_attempts,
            error = $5,
            locked_at = NULL,
            worker_id = NULL,
            next_attempt_at = NULL,
            updated_at = now()
        WHERE payload::jsonb ->> 'project_id' = $1
          AND task_type = ANY($2::text[])
          AND NOT (status = ANY($3::text[]))
        """,
        project_id,
        list(CANCELLABLE_KNOWLEDGE_JOB_TYPES),
        list(TERMINAL_QUEUE_STATUSES),
        CLEANUP_QUEUE_STATUS,
        CLEANUP_QUEUE_ERROR,
    )


async def _cleanup_document_surface_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
    document_id: str,
) -> tuple[int, int, int, int]:
    surface_relations = 0
    surface_cards = 0
    surface_source_units = 0
    surface_runs = 0

    for table in (
        "knowledge_surface_rejected_questions",
        "knowledge_surface_question_reassignments",
        "knowledge_surface_question_ownership",
        "knowledge_surface_merge_decisions",
        "knowledge_surface_global_relations",
        "knowledge_surface_local_relations",
        "knowledge_surface_relations",
    ):
        surface_relations += await _execute_count(
            conn,
            f"""
            DELETE FROM {table}
            WHERE document_id = $1
            """,
            document_id,
        )

    for table in (
        "knowledge_surface_answer_drafts",
        "knowledge_surface_candidates",
        "knowledge_surfaces",
        "knowledge_surface_reconciliation_runs",
    ):
        surface_cards += await _execute_count(
            conn,
            f"""
            DELETE FROM {table}
            WHERE document_id = $1
            """,
            document_id,
        )

    surface_source_units += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_surface_source_units
        WHERE document_id = $1
        """,
        document_id,
    )
    surface_runs += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_surface_compiler_stages
        WHERE document_id = $1
        """,
        document_id,
    )
    surface_runs += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_surface_compiler_runs
        WHERE document_id = $1
        """,
        document_id,
    )

    return surface_runs, surface_source_units, surface_cards, surface_relations


async def _cleanup_project_surface_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
) -> tuple[int, int, int, int]:
    surface_relations = 0
    surface_cards = 0
    surface_source_units = 0
    surface_runs = 0

    for table in (
        "knowledge_surface_rejected_questions",
        "knowledge_surface_question_reassignments",
        "knowledge_surface_question_ownership",
        "knowledge_surface_merge_decisions",
        "knowledge_surface_global_relations",
        "knowledge_surface_local_relations",
        "knowledge_surface_relations",
    ):
        surface_relations += await _execute_count(
            conn,
            f"""
            DELETE FROM {table}
            WHERE document_id IN (SELECT id FROM knowledge_documents WHERE project_id = $1)
            """,
            project_id,
        )

    for table in (
        "knowledge_surface_answer_drafts",
        "knowledge_surface_candidates",
        "knowledge_surfaces",
        "knowledge_surface_reconciliation_runs",
    ):
        surface_cards += await _execute_count(
            conn,
            f"""
            DELETE FROM {table}
            WHERE document_id IN (SELECT id FROM knowledge_documents WHERE project_id = $1)
            """,
            project_id,
        )

    surface_source_units += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_surface_source_units
        WHERE run_id IN (
            SELECT id
            FROM knowledge_surface_compiler_runs
            WHERE document_id IN (SELECT id FROM knowledge_documents WHERE project_id = $1)
        )
        """,
        project_id,
    )
    surface_runs += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_surface_compiler_stages
        WHERE run_id IN (
            SELECT id
            FROM knowledge_surface_compiler_runs
            WHERE document_id IN (SELECT id FROM knowledge_documents WHERE project_id = $1)
        )
        """,
        project_id,
    )
    surface_runs += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_surface_compiler_runs
        WHERE document_id IN (SELECT id FROM knowledge_documents WHERE project_id = $1)
        """,
        project_id,
    )

    return surface_runs, surface_source_units, surface_cards, surface_relations


async def _cleanup_document_rag_eval_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
    document_id: str,
) -> int:
    del project_id
    total = 0

    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_review_groups
        WHERE document_id = $1
        """,
        document_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_question_reviews
        WHERE document_id = $1
        """,
        document_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_results
        WHERE run_id IN (
            SELECT id FROM rag_eval_runs WHERE document_id = $1
        )
        OR question_id IN (
            SELECT id FROM rag_eval_questions WHERE document_id = $1
        )
        """,
        document_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_runs
        WHERE document_id = $1
        """,
        document_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_questions
        WHERE document_id = $1
        """,
        document_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_datasets
        WHERE document_id = $1
        """,
        document_id,
    )
    return total


async def _cleanup_project_rag_eval_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
) -> int:
    total = 0

    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_review_groups
        WHERE project_id = $1
        OR document_id IN (
            SELECT id FROM knowledge_documents WHERE project_id = $1
        )
        """,
        project_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_question_reviews
        WHERE project_id = $1
        OR document_id IN (
            SELECT id FROM knowledge_documents WHERE project_id = $1
        )
        """,
        project_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_results
        WHERE run_id IN (
            SELECT id
            FROM rag_eval_runs
            WHERE project_id = $1
               OR document_id IN (
                   SELECT id FROM knowledge_documents WHERE project_id = $1
               )
        )
        OR question_id IN (
            SELECT id
            FROM rag_eval_questions
            WHERE project_id = $1
               OR document_id IN (
                   SELECT id FROM knowledge_documents WHERE project_id = $1
               )
        )
        """,
        project_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_runs
        WHERE project_id = $1
        OR document_id IN (
            SELECT id FROM knowledge_documents WHERE project_id = $1
        )
        """,
        project_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_questions
        WHERE project_id = $1
        OR document_id IN (
            SELECT id FROM knowledge_documents WHERE project_id = $1
        )
        """,
        project_id,
    )
    total += await _execute_count(
        conn,
        """
        DELETE FROM rag_eval_datasets
        WHERE project_id = $1
        OR document_id IN (
            SELECT id FROM knowledge_documents WHERE project_id = $1
        )
        """,
        project_id,
    )
    return total


async def _cleanup_document_entry_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
    document_id: str,
) -> tuple[int, int, int, int, int]:
    entry_source_refs = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_entry_source_refs
        WHERE entry_id IN (
            SELECT id
            FROM knowledge_entries
            WHERE project_id = $1
              AND document_id = $2
        )
        OR source_chunk_id IN (
            SELECT id
            FROM knowledge_source_chunks
            WHERE project_id = $1
              AND document_id = $2
        )
        """,
        project_id,
        document_id,
    )
    retrieval_surface_rows = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_retrieval_surface
        WHERE project_id = $1
          AND document_id = $2
        """,
        project_id,
        document_id,
    )
    entry_versions = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_entry_versions
        WHERE project_id = $1
          AND (
            document_id = $2
            OR entry_id IN (
                SELECT id
                FROM knowledge_entries
                WHERE project_id = $1
                  AND document_id = $2
            )
          )
        """,
        project_id,
        document_id,
    )
    edit_actions = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_edit_actions
        WHERE project_id = $1
          AND (
            document_id = $2
            OR target_entry_id IN (
                SELECT id
                FROM knowledge_entries
                WHERE project_id = $1
                  AND document_id = $2
            )
          )
        """,
        project_id,
        document_id,
    )
    entries = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_entries
        WHERE project_id = $1
          AND document_id = $2
        """,
        project_id,
        document_id,
    )

    return (
        entry_source_refs,
        retrieval_surface_rows,
        entry_versions,
        edit_actions,
        entries,
    )


async def _cleanup_project_entry_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
) -> tuple[int, int, int, int, int]:
    entry_source_refs = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_entry_source_refs
        WHERE entry_id IN (
            SELECT id
            FROM knowledge_entries
            WHERE project_id = $1
        )
        OR source_chunk_id IN (
            SELECT id
            FROM knowledge_source_chunks
            WHERE project_id = $1
        )
        """,
        project_id,
    )
    retrieval_surface_rows = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_retrieval_surface
        WHERE project_id = $1
        """,
        project_id,
    )
    entry_versions = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_entry_versions
        WHERE project_id = $1
        """,
        project_id,
    )
    edit_actions = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_edit_actions
        WHERE project_id = $1
        """,
        project_id,
    )
    entries = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_entries
        WHERE project_id = $1
        """,
        project_id,
    )

    return (
        entry_source_refs,
        retrieval_surface_rows,
        entry_versions,
        edit_actions,
        entries,
    )


async def _cleanup_document_compiler_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
    document_id: str,
) -> tuple[int, int, int, int, int]:
    candidate_clusters = 0
    compiler_batches = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_compiler_batches
        WHERE project_id = $1
          AND document_id = $2
        """,
        project_id,
        document_id,
    )
    await _execute_count(
        conn,
        """
        DELETE FROM knowledge_compilation_metrics
        WHERE compiler_run_id IN (
            SELECT id
            FROM knowledge_compiler_runs
            WHERE project_id = $1
              AND document_id = $2
        )
        """,
        project_id,
        document_id,
    )
    candidate_clusters += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_candidate_cluster_members
        WHERE cluster_id IN (
            SELECT id
            FROM knowledge_candidate_clusters
            WHERE project_id = $1
              AND document_id = $2
        )
        OR candidate_id IN (
            SELECT id
            FROM knowledge_answer_candidates
            WHERE project_id = $1
              AND document_id = $2
        )
        """,
        project_id,
        document_id,
    )
    answer_candidates = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_answer_candidates
        WHERE project_id = $1
          AND document_id = $2
        """,
        project_id,
        document_id,
    )
    candidate_clusters += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_candidate_clusters
        WHERE project_id = $1
          AND document_id = $2
        """,
        project_id,
        document_id,
    )
    compiler_runs = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_compiler_runs
        WHERE project_id = $1
          AND document_id = $2
        """,
        project_id,
        document_id,
    )

    return compiler_runs, compiler_batches, answer_candidates, candidate_clusters, 0


async def _cleanup_project_compiler_artifacts(
    conn: ConnectionLike,
    *,
    project_id: str,
) -> tuple[int, int, int, int, int]:
    candidate_clusters = 0
    compiler_batches = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_compiler_batches
        WHERE project_id = $1
        """,
        project_id,
    )
    await _execute_count(
        conn,
        """
        DELETE FROM knowledge_compilation_metrics
        WHERE compiler_run_id IN (
            SELECT id
            FROM knowledge_compiler_runs
            WHERE project_id = $1
        )
        """,
        project_id,
    )
    candidate_clusters += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_candidate_cluster_members
        WHERE cluster_id IN (
            SELECT id
            FROM knowledge_candidate_clusters
            WHERE project_id = $1
        )
        OR candidate_id IN (
            SELECT id
            FROM knowledge_answer_candidates
            WHERE project_id = $1
        )
        """,
        project_id,
    )
    answer_candidates = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_answer_candidates
        WHERE project_id = $1
        """,
        project_id,
    )
    candidate_clusters += await _execute_count(
        conn,
        """
        DELETE FROM knowledge_candidate_clusters
        WHERE project_id = $1
        """,
        project_id,
    )
    compiler_runs = await _execute_count(
        conn,
        """
        DELETE FROM knowledge_compiler_runs
        WHERE project_id = $1
        """,
        project_id,
    )

    return compiler_runs, compiler_batches, answer_candidates, candidate_clusters, 0


async def cleanup_document_artifacts(
    conn_or_pool: ConnectionOrPool,
    *,
    project_id: str,
    document_id: str,
    plan: KnowledgeArtifactCleanupPlan,
) -> KnowledgeArtifactCleanupResult:
    if not plan.destructive:
        return KnowledgeArtifactCleanupResult(
            plan=plan,
            warnings=(
                "non-destructive cleanup plan skipped by infrastructure cleanup",
            ),
        )

    async with _acquire_connection(conn_or_pool) as conn:
        async with conn.transaction():
            execution_queue_jobs = await _cancel_document_queue_jobs(
                conn,
                document_id=document_id,
            )

            (
                surface_runs,
                surface_source_units,
                surface_cards,
                surface_relations,
            ) = await _cleanup_document_surface_artifacts(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

            rag_eval_artifacts = await _cleanup_document_rag_eval_artifacts(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

            (
                entry_source_refs,
                retrieval_surface_rows,
                entry_versions,
                edit_actions,
                entries,
            ) = await _cleanup_document_entry_artifacts(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

            (
                compiler_runs,
                compiler_batches,
                answer_candidates,
                candidate_clusters,
                _compiler_auxiliary,
            ) = await _cleanup_document_compiler_artifacts(
                conn,
                project_id=project_id,
                document_id=document_id,
            )

            source_chunks = await _execute_count(
                conn,
                """
                DELETE FROM knowledge_source_chunks
                WHERE project_id = $1
                  AND document_id = $2
                """,
                project_id,
                document_id,
            )

            legacy_runtime_rows = await _execute_count(
                conn,
                """
                DELETE FROM knowledge_base
                WHERE project_id = $1
                  AND document_id = $2
                """,
                project_id,
                document_id,
            )

            documents = 0
            if plan.delete_document_row:
                documents = await _execute_count(
                    conn,
                    """
                    DELETE FROM knowledge_documents
                    WHERE project_id = $1
                      AND id = $2
                    """,
                    project_id,
                    document_id,
                )
            elif plan.reset_document_state:
                documents = await _execute_count(
                    conn,
                    """
                    UPDATE knowledge_documents
                    SET
                        status = 'pending',
                        preprocessing_status = 'not_requested',
                        preprocessing_error = NULL,
                        preprocessing_model = NULL,
                        preprocessing_prompt_version = NULL,
                        preprocessing_metrics = '{}'::jsonb,
                        updated_at = now()
                    WHERE project_id = $1
                      AND id = $2
                    """,
                    project_id,
                    document_id,
                )

    return KnowledgeArtifactCleanupResult(
        plan=plan,
        counters=KnowledgeArtifactCleanupCounters(
            documents=documents,
            legacy_runtime_rows=legacy_runtime_rows,
            source_chunks=source_chunks,
            entries=entries,
            entry_source_refs=entry_source_refs,
            retrieval_surface_rows=retrieval_surface_rows,
            entry_versions=entry_versions,
            edit_actions=edit_actions,
            compiler_runs=compiler_runs,
            compiler_batches=compiler_batches,
            answer_candidates=answer_candidates,
            candidate_clusters=candidate_clusters,
            surface_runs=surface_runs,
            surface_source_units=surface_source_units,
            surface_cards=surface_cards,
            surface_relations=surface_relations,
            rag_eval_artifacts=rag_eval_artifacts,
            execution_queue_jobs=execution_queue_jobs,
        ),
    )


async def cleanup_project_artifacts(
    conn_or_pool: ConnectionOrPool,
    *,
    project_id: str,
    plan: KnowledgeArtifactCleanupPlan,
) -> KnowledgeArtifactCleanupResult:
    if not plan.destructive:
        return KnowledgeArtifactCleanupResult(
            plan=plan,
            warnings=(
                "non-destructive cleanup plan skipped by infrastructure cleanup",
            ),
        )

    async with _acquire_connection(conn_or_pool) as conn:
        async with conn.transaction():
            execution_queue_jobs = await _cancel_project_queue_jobs(
                conn,
                project_id=project_id,
            )

            (
                surface_runs,
                surface_source_units,
                surface_cards,
                surface_relations,
            ) = await _cleanup_project_surface_artifacts(
                conn,
                project_id=project_id,
            )

            rag_eval_artifacts = await _cleanup_project_rag_eval_artifacts(
                conn,
                project_id=project_id,
            )

            (
                entry_source_refs,
                retrieval_surface_rows,
                entry_versions,
                edit_actions,
                entries,
            ) = await _cleanup_project_entry_artifacts(
                conn,
                project_id=project_id,
            )

            (
                compiler_runs,
                compiler_batches,
                answer_candidates,
                candidate_clusters,
                _compiler_auxiliary,
            ) = await _cleanup_project_compiler_artifacts(
                conn,
                project_id=project_id,
            )

            source_chunks = await _execute_count(
                conn,
                """
                DELETE FROM knowledge_source_chunks
                WHERE project_id = $1
                """,
                project_id,
            )

            legacy_runtime_rows = await _execute_count(
                conn,
                """
                DELETE FROM knowledge_base
                WHERE project_id = $1
                """,
                project_id,
            )

            documents = 0
            if plan.clear_project_documents:
                documents = await _execute_count(
                    conn,
                    """
                    DELETE FROM knowledge_documents
                    WHERE project_id = $1
                    """,
                    project_id,
                )

    return KnowledgeArtifactCleanupResult(
        plan=plan,
        counters=KnowledgeArtifactCleanupCounters(
            documents=documents,
            legacy_runtime_rows=legacy_runtime_rows,
            source_chunks=source_chunks,
            entries=entries,
            entry_source_refs=entry_source_refs,
            retrieval_surface_rows=retrieval_surface_rows,
            entry_versions=entry_versions,
            edit_actions=edit_actions,
            compiler_runs=compiler_runs,
            compiler_batches=compiler_batches,
            answer_candidates=answer_candidates,
            candidate_clusters=candidate_clusters,
            surface_runs=surface_runs,
            surface_source_units=surface_source_units,
            surface_cards=surface_cards,
            surface_relations=surface_relations,
            rag_eval_artifacts=rag_eval_artifacts,
            execution_queue_jobs=execution_queue_jobs,
        ),
    )
