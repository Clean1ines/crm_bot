from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, cast

import asyncpg

from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.domain.project_plane.knowledge_views import SourceRefView
from src.application.rag_eval.schemas import (
    JsonObject,
    RagEvalChunk,
    RagEvalDataset,
    RagEvalQuestion,
    RagEvalQuestionType,
    RagEvalResult,
    RagEvalRun,
    RagEvalStatus,
    RagQualityReport,
    RagEvalSeverity,
)


def _jsonb(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)

    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return cast(dict[str, object], decoded)

    return {}


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return decoded

    return []


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


def _row_int_value(row: Mapping[str, object], key: str, default: int = 0) -> int:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _row_float_value(
    row: Mapping[str, object], key: str, default: float = 0.0
) -> float:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _row_datetime_value(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if isinstance(value, datetime):
        return value
    raise ValueError(f"Expected datetime field {key}")


def _row_optional_datetime_value(
    row: Mapping[str, object], key: str
) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raise ValueError(f"Expected optional datetime field {key}")


def _source_ref_views_from_payload(value: object) -> tuple[SourceRefView, ...]:
    if not isinstance(value, list):
        return ()

    refs: list[SourceRefView] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        quote = " ".join(str(item.get("quote") or "").strip().split())
        if not quote:
            continue
        source_chunk_id = item.get("source_chunk_id")
        refs.append(
            SourceRefView(
                source_index=_row_int_value(item, "source_index", 0),
                quote=quote,
                source_chunk_id=str(source_chunk_id) if source_chunk_id else None,
                start_offset=_row_int_value(item, "start_offset", 0)
                if item.get("start_offset") is not None
                else None,
                end_offset=_row_int_value(item, "end_offset", 0)
                if item.get("end_offset") is not None
                else None,
                confidence=_row_float_value(item, "confidence", 0.0)
                if item.get("confidence") is not None
                else None,
            )
        )
    return tuple(refs)


RAG_EVAL_SOURCE_ENTRY_KINDS = tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))


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
                    rs.entry_id AS id,
                    rs.answer AS content,
                    rs.document_id,
                    d.file_name AS source,
                    rs.entry_kind,
                    rs.title,
                    rs.source_refs,
                    rs.embedding_text,
                    rs.enrichment->'questions' AS questions,
                    rs.enrichment->'synonyms' AS synonyms,
                    rs.enrichment->'tags' AS tags
                FROM knowledge_retrieval_surface AS rs
                JOIN knowledge_documents AS d ON d.id = rs.document_id
                WHERE rs.project_id = $1::uuid
                  AND rs.document_id = $2::uuid
                  AND rs.entry_kind = ANY($3::text[])
                  AND rs.status = 'published'
                  AND rs.visibility = 'runtime'
                  AND d.status = 'processed'
                ORDER BY rs.created_at ASC NULLS LAST, rs.entry_id ASC
                """,
                project_id,
                document_id,
                list(RAG_EVAL_SOURCE_ENTRY_KINDS),
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

    async def get_latest_ready_dataset_with_questions(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> RagEvalDataset | None:
        async with self.pool.acquire() as conn:
            dataset_row = await conn.fetchrow(
                """
                SELECT
                    id,
                    project_id,
                    document_id,
                    status,
                    generated_at,
                    model_used,
                    total_questions,
                    metadata
                FROM rag_eval_datasets
                WHERE project_id = $1::uuid
                  AND document_id = $2::uuid
                  AND status = 'ready'
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                project_id,
                document_id,
            )

            if dataset_row is None:
                return None

            question_rows = await conn.fetch(
                """
                SELECT
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
                FROM rag_eval_questions
                WHERE dataset_id = $1
                  AND project_id = $2::uuid
                  AND document_id = $3::uuid
                ORDER BY created_at ASC, id ASC
                """,
                str(dataset_row["id"]),
                project_id,
                document_id,
            )

        dataset = RagEvalDataset(
            id=str(dataset_row["id"]),
            project_id=str(dataset_row["project_id"]),
            document_id=str(dataset_row["document_id"]),
            status=cast(RagEvalStatus, str(dataset_row["status"])),
            model_used=str(dataset_row["model_used"] or ""),
            total_questions=_row_int_value(dataset_row, "total_questions", 0),
            generated_at=dataset_row["generated_at"],
            metadata=_json_object(dataset_row["metadata"]),
            questions=[self._question_from_row(row) for row in question_rows],
        )
        dataset.total_questions = len(dataset.questions)
        return dataset

    async def get_latest_resumable_run(
        self,
        *,
        project_id: str,
        document_id: str,
        dataset_id: str,
    ) -> RagEvalRun | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
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
                FROM rag_eval_runs
                WHERE project_id = $1::uuid
                  AND document_id = $2::uuid
                  AND dataset_id = $3
                  AND status IN ('running', 'failed')
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                project_id,
                document_id,
                dataset_id,
            )

        if row is None:
            return None

        return RagEvalRun(
            id=str(row["id"]),
            dataset_id=str(row["dataset_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            status=cast(RagEvalStatus, str(row["status"])),
            started_at=_row_datetime_value(row, "started_at"),
            finished_at=_row_optional_datetime_value(row, "finished_at"),
            retriever_version=str(row["retriever_version"] or "production_rag"),
            reranker_version=str(row["reranker_version"] or "production_rag"),
            generator_model=str(row["generator_model"] or ""),
        )

    async def load_run_results(self, *, run_id: str) -> list[RagEvalResult]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    rr.id,
                    rr.run_id,
                    rr.question_id,
                    rr.retrieved_chunk_ids,
                    rr.top1_hit,
                    rr.top3_hit,
                    rr.top5_hit,
                    rr.expected_chunk_found,
                    rr.wrong_chunk_top1,
                    rr.answer_text,
                    rr.answer_supported,
                    rr.hallucination_risk,
                    rr.should_answer_passed,
                    rr.score,
                    rr.notes,
                    rr.judge_json,
                    rr.latency_ms,
                    rr.created_at,
                    q.id AS q_id,
                    q.dataset_id AS q_dataset_id,
                    q.project_id AS q_project_id,
                    q.document_id AS q_document_id,
                    q.question AS q_question,
                    q.question_type AS q_question_type,
                    q.expected_chunk_ids AS q_expected_chunk_ids,
                    q.expected_answer_summary AS q_expected_answer_summary,
                    q.should_answer AS q_should_answer,
                    q.should_escalate AS q_should_escalate,
                    q.difficulty AS q_difficulty,
                    q.severity AS q_severity,
                    q.source AS q_source,
                    q.metadata AS q_metadata,
                    q.created_at AS q_created_at
                FROM rag_eval_results AS rr
                JOIN rag_eval_questions AS q ON q.id = rr.question_id
                WHERE rr.run_id = $1
                ORDER BY rr.created_at ASC, rr.id ASC
                """,
                run_id,
            )

        return [self._result_from_joined_row(row) for row in rows]

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
        source_refs = _source_ref_views_from_payload(row.get("source_refs"))
        source_excerpt = source_refs[0].quote if source_refs else ""
        return RagEvalChunk(
            id=str(row["id"]),
            content=str(row["content"] or ""),
            document_id=_optional_text(row, "document_id"),
            source=_optional_text(row, "source"),
            source_refs=source_refs,
            metadata={
                "entry_kind": row.get("entry_kind"),
                "title": row.get("title"),
                "source_excerpt": source_excerpt,
                "source_refs": [source_ref.to_dict() for source_ref in source_refs],
                "embedding_text": row.get("embedding_text"),
                "questions": row.get("questions"),
                "synonyms": row.get("synonyms"),
                "tags": row.get("tags"),
            },
        )

    def _question_from_row(self, row: Mapping[str, object]) -> RagEvalQuestion:
        expected_chunk_ids = [
            str(item)
            for item in _json_list(row.get("expected_chunk_ids"))
            if str(item).strip()
        ]

        return RagEvalQuestion(
            id=str(row["id"]),
            dataset_id=str(row["dataset_id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            question=str(row["question"] or ""),
            question_type=cast(
                RagEvalQuestionType, str(row["question_type"] or "direct")
            ),
            expected_chunk_ids=expected_chunk_ids,
            expected_answer_summary=str(row["expected_answer_summary"] or ""),
            should_answer=bool(row["should_answer"]),
            should_escalate=bool(row["should_escalate"]),
            difficulty=_row_int_value(row, "difficulty", 1),
            severity=cast(RagEvalSeverity, str(row["severity"] or "medium")),
            source=str(row["source"] or "llm_generated"),
            metadata=_json_object(row.get("metadata")),
            created_at=_row_datetime_value(row, "created_at"),
        )

    def _question_from_joined_result_row(
        self,
        row: Mapping[str, object],
    ) -> RagEvalQuestion:
        expected_chunk_ids = [
            str(item)
            for item in _json_list(row.get("q_expected_chunk_ids"))
            if str(item).strip()
        ]

        return RagEvalQuestion(
            id=str(row["q_id"]),
            dataset_id=str(row["q_dataset_id"]),
            project_id=str(row["q_project_id"]),
            document_id=str(row["q_document_id"]),
            question=str(row["q_question"] or ""),
            question_type=cast(
                RagEvalQuestionType,
                str(row["q_question_type"] or "direct"),
            ),
            expected_chunk_ids=expected_chunk_ids,
            expected_answer_summary=str(row["q_expected_answer_summary"] or ""),
            should_answer=bool(row["q_should_answer"]),
            should_escalate=bool(row["q_should_escalate"]),
            difficulty=_row_int_value(row, "q_difficulty", 1),
            severity=cast(RagEvalSeverity, str(row["q_severity"] or "medium")),
            source=str(row["q_source"] or "llm_generated"),
            metadata=_json_object(row.get("q_metadata")),
            created_at=_row_datetime_value(row, "q_created_at"),
        )

    def _result_from_joined_row(self, row: Mapping[str, object]) -> RagEvalResult:
        return RagEvalResult(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            question_id=str(row["question_id"]),
            question=self._question_from_joined_result_row(row),
            retrieved_chunks=[],
            answer_text=str(row["answer_text"] or ""),
            top1_hit=bool(row["top1_hit"]),
            top3_hit=bool(row["top3_hit"]),
            top5_hit=bool(row["top5_hit"]),
            expected_chunk_found=bool(row["expected_chunk_found"]),
            wrong_chunk_top1=bool(row["wrong_chunk_top1"]),
            answer_supported=bool(row["answer_supported"]),
            hallucination_risk=cast(
                Literal["low", "medium", "high"],
                str(row["hallucination_risk"] or "medium"),
            ),
            should_answer_passed=bool(row["should_answer_passed"]),
            score=_row_float_value(row, "score", 0.0),
            notes=str(row["notes"] or ""),
            judge_json=cast(JsonObject, _json_object(row.get("judge_json"))),
            latency_ms=_row_int_value(row, "latency_ms", 0),
            created_at=_row_datetime_value(row, "created_at"),
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
