from __future__ import annotations

import json
from collections.abc import Mapping

import asyncpg

from src.domain.project_plane.knowledge_compilation import (
    CompilationMetrics,
    CompilerBatch,
    CompilerRun,
)
from src.infrastructure.db.repositories.knowledge_compiler_payloads import (
    compiler_jsonb_array_payload,
    compiler_metrics_payload,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import jsonb_object_payload
from src.utils.uuid_utils import ensure_uuid


async def upsert_compiler_run(
    conn: asyncpg.Connection,
    *,
    run: CompilerRun,
) -> None:
    metrics_payload = compiler_metrics_payload(run.metrics)
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
    await upsert_compilation_metrics(
        conn,
        compiler_run_id=run.id,
        metrics=run.metrics,
        metrics_payload=metrics_payload,
    )


async def upsert_compiler_batch(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    batch: CompilerBatch,
) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_compiler_batches (
            id,
            project_id,
            document_id,
            compiler_run_id,
            batch_index,
            batch_count,
            source_chunk_ids,
            source_chunk_indexes,
            status,
            attempt_count,
            model,
            prompt_version,
            tokens_input,
            tokens_output,
            tokens_total,
            error_type,
            error_message,
            metadata
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7::jsonb,
            $8::jsonb,
            $9,
            $10,
            $11,
            $12,
            $13,
            $14,
            $15,
            $16,
            $17,
            $18::jsonb
        )
        ON CONFLICT (id)
        DO UPDATE SET
            batch_index = EXCLUDED.batch_index,
            batch_count = EXCLUDED.batch_count,
            source_chunk_ids = EXCLUDED.source_chunk_ids,
            source_chunk_indexes = EXCLUDED.source_chunk_indexes,
            status = EXCLUDED.status,
            attempt_count = EXCLUDED.attempt_count,
            model = EXCLUDED.model,
            prompt_version = EXCLUDED.prompt_version,
            tokens_input = EXCLUDED.tokens_input,
            tokens_output = EXCLUDED.tokens_output,
            tokens_total = EXCLUDED.tokens_total,
            error_type = EXCLUDED.error_type,
            error_message = EXCLUDED.error_message,
            metadata = EXCLUDED.metadata,
            updated_at = now()
        """,
        batch.id,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        batch.compiler_run_id,
        batch.batch_index,
        batch.batch_count,
        compiler_jsonb_array_payload(
            [
                {"source_chunk_id": source_chunk_id}
                for source_chunk_id in batch.source_chunk_ids
            ]
        ),
        json.dumps(list(batch.source_chunk_indexes), ensure_ascii=False),
        batch.status.value,
        batch.attempt_count,
        batch.model,
        batch.prompt_version,
        batch.tokens_input,
        batch.tokens_output,
        batch.tokens_total,
        batch.error_type,
        batch.error_message,
        jsonb_object_payload(batch.metadata),
    )


async def mark_compiler_batch_processing(
    conn: asyncpg.Connection,
    batch_id: str,
    *,
    attempt_count: int,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_compiler_batches AS batch
        SET status = 'processing',
            attempt_count = $2,
            started_at = COALESCE(started_at, now()),
            finished_at = NULL,
            error_type = '',
            error_message = '',
            updated_at = now()
        FROM knowledge_documents AS doc
        WHERE batch.id = $1
          AND doc.id = batch.document_id
          AND doc.status <> 'error'
          AND COALESCE(doc.preprocessing_status, '') NOT IN ('failed', 'cancelled')
        """,
        batch_id,
        attempt_count,
    )


async def complete_compiler_batch(
    conn: asyncpg.Connection,
    batch_id: str,
    *,
    model: str,
    prompt_version: str,
    tokens_input: int,
    tokens_output: int,
    tokens_total: int,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_compiler_batches AS batch
        SET status = 'completed',
            model = $2,
            prompt_version = $3,
            tokens_input = $4,
            tokens_output = $5,
            tokens_total = $6,
            error_type = '',
            error_message = '',
            finished_at = now(),
            updated_at = now()
        FROM knowledge_documents AS doc
        WHERE batch.id = $1
          AND doc.id = batch.document_id
          AND doc.status <> 'error'
          AND COALESCE(doc.preprocessing_status, '') NOT IN ('failed', 'cancelled')
        """,
        batch_id,
        model,
        prompt_version,
        tokens_input,
        tokens_output,
        tokens_total,
    )


async def fail_compiler_batch(
    conn: asyncpg.Connection,
    batch_id: str,
    *,
    error_type: str,
    error_message: str,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_compiler_batches
        SET status = 'failed',
            error_type = $2,
            error_message = $3,
            finished_at = now(),
            updated_at = now()
        WHERE id = $1
        """,
        batch_id,
        error_type,
        error_message,
    )


async def complete_compiler_run(
    conn: asyncpg.Connection,
    compiler_run_id: str,
    *,
    metrics: CompilationMetrics,
) -> None:
    metrics_payload = compiler_metrics_payload(metrics)
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
    await upsert_compilation_metrics(
        conn,
        compiler_run_id=compiler_run_id,
        metrics=metrics,
        metrics_payload=metrics_payload,
    )


async def fail_compiler_run(
    conn: asyncpg.Connection,
    compiler_run_id: str,
    *,
    error: str,
) -> None:
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


async def upsert_compilation_metrics(
    conn: asyncpg.Connection,
    *,
    compiler_run_id: str,
    metrics: CompilationMetrics,
    metrics_payload: Mapping[str, object] | None = None,
) -> None:
    payload = (
        compiler_metrics_payload(metrics)
        if metrics_payload is None
        else metrics_payload
    )
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
            retrieval_surface_count,
            retrieval_question_count,
            runtime_entry_count,
            qa_eval_pass_rate,
            latency_ms,
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
            $14,
            $15::jsonb
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
            retrieval_surface_count = EXCLUDED.retrieval_surface_count,
            retrieval_question_count = EXCLUDED.retrieval_question_count,
            runtime_entry_count = EXCLUDED.runtime_entry_count,
            qa_eval_pass_rate = EXCLUDED.qa_eval_pass_rate,
            latency_ms = EXCLUDED.latency_ms,
            metrics = EXCLUDED.metrics
        """,
        ensure_uuid(compiler_run_id),
        metrics.source_chunk_count,
        metrics.answer_candidate_count,
        metrics.grounded_candidate_count,
        metrics.rejected_candidate_count,
        metrics.candidate_cluster_count,
        metrics.canonical_entry_count,
        metrics.enriched_entry_count,
        metrics.embedded_entry_count,
        metrics.retrieval_surface_count,
        metrics.retrieval_question_count,
        metrics.runtime_entry_count,
        metrics.qa_eval_pass_rate,
        metrics.latency_ms,
        json.dumps(payload, ensure_ascii=False),
    )
