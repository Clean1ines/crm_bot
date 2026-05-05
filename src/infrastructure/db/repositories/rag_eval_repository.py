from __future__ import annotations

import json
from collections.abc import Mapping

import asyncpg

from src.application.rag_eval.schemas import (
    JsonObject,
    RagEvalChunk,
    RagEvalDataset,
    RagEvalQuestion,
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
)


def _jsonb(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def _row_float(
    row: Mapping[str, object], key: str, default: float = 0.0
) -> float | None:
    value = row.get(key)
    if value is None:
        return default
    try:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return None
        return float(value)
    except (TypeError, ValueError):
        return default


class RagEvalRepository:
    """Postgres adapter for automatic RAG quality evaluation artifacts.

    Stores generated eval datasets, questions, runs, per-question results and
    final quality reports. This repository deliberately does not call LLMs and
    does not run RAG itself.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def load_document_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalChunk]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    kb.id,
                    kb.content,
                    kb.document_id,
                    d.file_name AS source,
                    kb.entry_type,
                    kb.title,
                    kb.source_excerpt,
                    kb.embedding_text,
                    kb.questions,
                    kb.synonyms,
                    kb.tags
                FROM knowledge_base AS kb
                JOIN knowledge_documents AS d ON d.id = kb.document_id
                WHERE kb.project_id = $1::uuid
                  AND kb.document_id = $2::uuid
                  AND d.status = 'processed'
                ORDER BY kb.created_at ASC NULLS LAST, kb.id ASC
                """,
                project_id,
                document_id,
            )

        return [self._chunk_from_row(row) for row in rows]

    async def save_dataset(self, *, dataset: RagEvalDataset) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_eval_datasets (
                    id,
                    project_id,
                    document_id,
                    status,
                    generated_at,
                    model_used,
                    total_questions,
                    metadata
                )
                VALUES (
                    $1,
                    $2::uuid,
                    $3::uuid,
                    $4,
                    $5,
                    $6,
                    $7,
                    $8::jsonb
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    generated_at = EXCLUDED.generated_at,
                    model_used = EXCLUDED.model_used,
                    total_questions = EXCLUDED.total_questions,
                    metadata = EXCLUDED.metadata
                """,
                dataset.id,
                dataset.project_id,
                dataset.document_id,
                dataset.status,
                dataset.generated_at,
                dataset.model_used,
                dataset.total_questions,
                _jsonb(dataset.metadata),
            )

            if dataset.questions:
                await conn.executemany(
                    """
                    INSERT INTO rag_eval_questions (
                        id,
                        dataset_id,
                        project_id,
                        document_id,
                        question,
                        question_type,
                        expected_chunk_ids,
                        expected_answer_summary,
                        should_answer,
                        should_escalate,
                        difficulty,
                        severity,
                        source,
                        metadata,
                        created_at
                    )
                    VALUES (
                        $1,
                        $2,
                        $3::uuid,
                        $4::uuid,
                        $5,
                        $6,
                        $7::jsonb,
                        $8,
                        $9,
                        $10,
                        $11,
                        $12,
                        $13,
                        $14::jsonb,
                        $15
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        question = EXCLUDED.question,
                        question_type = EXCLUDED.question_type,
                        expected_chunk_ids = EXCLUDED.expected_chunk_ids,
                        expected_answer_summary = EXCLUDED.expected_answer_summary,
                        should_answer = EXCLUDED.should_answer,
                        should_escalate = EXCLUDED.should_escalate,
                        difficulty = EXCLUDED.difficulty,
                        severity = EXCLUDED.severity,
                        source = EXCLUDED.source,
                        metadata = EXCLUDED.metadata
                    """,
                    [self._question_record(question) for question in dataset.questions],
                )

    async def create_run(self, *, run: RagEvalRun) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_eval_runs (
                    id,
                    dataset_id,
                    project_id,
                    document_id,
                    status,
                    started_at,
                    finished_at,
                    retriever_version,
                    reranker_version,
                    generator_model
                )
                VALUES (
                    $1,
                    $2,
                    $3::uuid,
                    $4::uuid,
                    $5,
                    $6,
                    $7,
                    $8,
                    $9,
                    $10
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    finished_at = EXCLUDED.finished_at,
                    retriever_version = EXCLUDED.retriever_version,
                    reranker_version = EXCLUDED.reranker_version,
                    generator_model = EXCLUDED.generator_model
                """,
                run.id,
                run.dataset_id,
                run.project_id,
                run.document_id,
                run.status,
                run.started_at,
                run.finished_at,
                run.retriever_version,
                run.reranker_version,
                run.generator_model,
            )

    async def save_result(self, *, result: RagEvalResult) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_eval_results (
                    id,
                    run_id,
                    question_id,
                    retrieved_chunk_ids,
                    top1_hit,
                    top3_hit,
                    top5_hit,
                    expected_chunk_found,
                    wrong_chunk_top1,
                    answer_text,
                    answer_supported,
                    hallucination_risk,
                    should_answer_passed,
                    score,
                    notes,
                    judge_json,
                    latency_ms,
                    created_at
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4::jsonb,
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
                    $15,
                    $16::jsonb,
                    $17,
                    $18
                )
                ON CONFLICT (id) DO UPDATE SET
                    retrieved_chunk_ids = EXCLUDED.retrieved_chunk_ids,
                    top1_hit = EXCLUDED.top1_hit,
                    top3_hit = EXCLUDED.top3_hit,
                    top5_hit = EXCLUDED.top5_hit,
                    expected_chunk_found = EXCLUDED.expected_chunk_found,
                    wrong_chunk_top1 = EXCLUDED.wrong_chunk_top1,
                    answer_text = EXCLUDED.answer_text,
                    answer_supported = EXCLUDED.answer_supported,
                    hallucination_risk = EXCLUDED.hallucination_risk,
                    should_answer_passed = EXCLUDED.should_answer_passed,
                    score = EXCLUDED.score,
                    notes = EXCLUDED.notes,
                    judge_json = EXCLUDED.judge_json,
                    latency_ms = EXCLUDED.latency_ms
                """,
                result.id,
                result.run_id,
                result.question_id,
                _jsonb([chunk.id for chunk in result.retrieved_chunks]),
                result.top1_hit,
                result.top3_hit,
                result.top5_hit,
                result.expected_chunk_found,
                result.wrong_chunk_top1,
                result.answer_text,
                result.answer_supported,
                result.hallucination_risk,
                result.should_answer_passed,
                result.score,
                result.notes,
                _jsonb(result.judge_json),
                result.latency_ms,
                result.created_at,
            )

    async def finish_run(self, *, run: RagEvalRun) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE rag_eval_runs
                SET status = $2,
                    finished_at = $3,
                    retriever_version = $4,
                    reranker_version = $5,
                    generator_model = $6
                WHERE id = $1
                """,
                run.id,
                run.status,
                run.finished_at,
                run.retriever_version,
                run.reranker_version,
                run.generator_model,
            )

    async def save_report(self, *, report: RagQualityReport) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_quality_reports (
                    id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    score,
                    readiness,
                    strengths,
                    problems,
                    recommendations,
                    metrics,
                    markdown,
                    created_at
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4::uuid,
                    $5::uuid,
                    $6,
                    $7,
                    $8::jsonb,
                    $9::jsonb,
                    $10::jsonb,
                    $11::jsonb,
                    $12,
                    $13
                )
                ON CONFLICT (id) DO UPDATE SET
                    score = EXCLUDED.score,
                    readiness = EXCLUDED.readiness,
                    strengths = EXCLUDED.strengths,
                    problems = EXCLUDED.problems,
                    recommendations = EXCLUDED.recommendations,
                    metrics = EXCLUDED.metrics,
                    markdown = EXCLUDED.markdown
                """,
                report.id,
                report.run_id,
                report.dataset_id,
                report.project_id,
                report.document_id,
                report.score,
                report.readiness,
                _jsonb(report.strengths),
                _jsonb(report.problems),
                _jsonb(report.recommendations),
                _jsonb(report.metrics),
                report.markdown,
                report.created_at,
            )

    async def get_latest_run_summary(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> JsonObject | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    r.id,
                    r.dataset_id,
                    r.project_id,
                    r.document_id,
                    r.status,
                    r.started_at,
                    r.finished_at,
                    r.retriever_version,
                    r.reranker_version,
                    r.generator_model,
                    COUNT(rr.id)::int AS result_count
                FROM rag_eval_runs AS r
                LEFT JOIN rag_eval_results AS rr ON rr.run_id = r.id
                WHERE r.project_id = $1::uuid
                  AND r.document_id = $2::uuid
                GROUP BY
                    r.id,
                    r.dataset_id,
                    r.project_id,
                    r.document_id,
                    r.status,
                    r.started_at,
                    r.finished_at,
                    r.retriever_version,
                    r.reranker_version,
                    r.generator_model
                ORDER BY r.started_at DESC, r.id DESC
                LIMIT 1
                """,
                project_id,
                document_id,
            )

        if row is None:
            return None

        started_at = row["started_at"]
        finished_at = row["finished_at"]

        return {
            "id": str(row["id"]),
            "dataset_id": str(row["dataset_id"]),
            "project_id": str(row["project_id"]),
            "document_id": str(row["document_id"]),
            "status": str(row["status"]),
            "started_at": started_at.isoformat()
            if hasattr(started_at, "isoformat")
            else str(started_at),
            "finished_at": finished_at.isoformat()
            if hasattr(finished_at, "isoformat")
            else (str(finished_at) if finished_at is not None else None),
            "retriever_version": str(row["retriever_version"]),
            "reranker_version": str(row["reranker_version"]),
            "generator_model": str(row["generator_model"] or ""),
            "result_count": int(row["result_count"] or 0),
        }

    async def get_latest_report(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> JsonObject | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    score,
                    readiness,
                    strengths,
                    problems,
                    recommendations,
                    metrics,
                    markdown,
                    created_at
                FROM rag_quality_reports
                WHERE project_id = $1::uuid
                  AND document_id = $2::uuid
                ORDER BY created_at DESC
                LIMIT 1
                """,
                project_id,
                document_id,
            )

        if row is None:
            return None

        return {
            "id": str(row["id"]),
            "run_id": str(row["run_id"]),
            "dataset_id": str(row["dataset_id"]),
            "project_id": str(row["project_id"]),
            "document_id": str(row["document_id"]),
            "score": _row_float(row, "score"),
            "readiness": str(row["readiness"]),
            "strengths": row["strengths"] or [],
            "problems": row["problems"] or [],
            "recommendations": row["recommendations"] or [],
            "metrics": row["metrics"] or {},
            "markdown": str(row["markdown"] or ""),
            "created_at": str(row["created_at"]),
        }

    def _chunk_from_row(self, row: Mapping[str, object]) -> RagEvalChunk:
        return RagEvalChunk(
            id=str(row["id"]),
            content=str(row["content"] or ""),
            document_id=_optional_text(row, "document_id"),
            source=_optional_text(row, "source"),
            metadata={
                "entry_type": row.get("entry_type"),
                "title": row.get("title"),
                "source_excerpt": row.get("source_excerpt"),
                "embedding_text": row.get("embedding_text"),
                "questions": row.get("questions"),
                "synonyms": row.get("synonyms"),
                "tags": row.get("tags"),
            },
        )

    def _question_record(self, question: RagEvalQuestion) -> tuple[object, ...]:
        return (
            question.id,
            question.dataset_id,
            question.project_id,
            question.document_id,
            question.question,
            question.question_type,
            _jsonb(question.expected_chunk_ids),
            question.expected_answer_summary,
            question.should_answer,
            question.should_escalate,
            question.difficulty,
            question.severity,
            question.source,
            _jsonb(question.metadata),
            question.created_at,
        )
