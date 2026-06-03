from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Literal, cast

import asyncpg

from src.domain.project_plane.json_types import JsonObject, JsonValue
from src.application.rag_eval.failure_classification import (
    KnowledgeEditAction,
    failure_classification_from_mapping,
    knowledge_edit_actions_from_value,
)
from src.application.rag_eval.schemas import (
    RagEvalDataset,
    RagEvalEvidenceEntry,
    RagEvalQuestion,
    RagEvalQuestionType,
    RagEvalResult,
    RagEvalRun,
    RagEvalSeverity,
    RagEvalStatus,
    RagQualityReport,
)
from src.domain.project_plane.knowledge_views import SourceRefView


def _jsonb(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)


def _optional_jsonb(value: object | None) -> str | None:
    if value is None:
        return None
    return _jsonb(value)


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
    for index, item in enumerate(value):
        if isinstance(item, str):
            quote = " ".join(item.strip().split())
            if not quote:
                continue
            refs.append(
                SourceRefView(
                    source_index=index,
                    quote=quote,
                    source_chunk_id=None,
                    start_offset=None,
                    end_offset=None,
                    confidence=None,
                )
            )
            continue

        if not isinstance(item, Mapping):
            continue

        quote = " ".join(str(item.get("quote") or "").strip().split())
        if not quote:
            continue

        source_chunk_id = item.get("source_chunk_id")
        refs.append(
            SourceRefView(
                source_index=_row_int_value(item, "source_index", index),
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


def _is_actionable_result(result: RagEvalResult) -> bool:
    return bool(result.proposed_actions) or (
        not result.is_passed and result.classification is not None
    )


def _actionable_action_payload(payload: Mapping[str, object]) -> JsonObject:
    question = payload.get("question")
    if isinstance(question, str) and question.strip():
        return {"question": question.strip()}
    return {}


def _actionable_action_summary(action: KnowledgeEditAction) -> JsonObject:
    summary: JsonObject = {
        "action_type": action.action_type.value,
        "reason": action.reason,
        "payload": _actionable_action_payload(action.payload),
    }
    if action.target_entry_id:
        summary["target_entry_id"] = action.target_entry_id
    return summary


def _result_summary(result: RagEvalResult) -> JsonObject:
    retrieved_entry_ids = [
        str(item) for item in _json_list(result.judge_json.get("retrieved_entry_ids"))
    ] or [entry.id for entry in result.retrieved_entries]
    return {
        "result_id": result.id,
        "run_id": result.run_id,
        "question_id": result.question_id,
        "question": result.question.question,
        "question_type": result.question.question_type,
        "expected_entry_ids": list(result.question.expected_entry_ids),
        "retrieved_entry_ids": _json_value(retrieved_entry_ids),
        "top1_hit": result.top1_hit,
        "top3_hit": result.top3_hit,
        "top5_hit": result.top5_hit,
        "expected_entry_found": result.expected_entry_found,
        "wrong_entry_top1": result.wrong_entry_top1,
        "answer_supported": result.answer_supported,
        "should_answer_passed": result.should_answer_passed,
        "hallucination_risk": result.hallucination_risk,
        "score": result.score,
        "notes": result.notes,
        "latency_ms": result.latency_ms,
        "created_at": result.created_at.isoformat(),
        "classification": _json_value(result.classification.to_json())
        if result.classification is not None
        else None,
        "proposed_actions": [
            _actionable_action_summary(action) for action in result.proposed_actions
        ],
    }


def _actionable_result_summary(result: RagEvalResult) -> JsonObject:
    return {
        "result_id": result.id,
        "run_id": result.run_id,
        "question_id": result.question_id,
        "question": result.question.question,
        "question_type": result.question.question_type,
        "expected_entry_ids": list(result.question.expected_entry_ids),
        "retrieved_entry_ids": [
            str(item)
            for item in _json_list(result.judge_json.get("retrieved_entry_ids"))
        ]
        or [entry.id for entry in result.retrieved_entries],
        "score": result.score,
        "answer_supported": result.answer_supported,
        "should_answer_passed": result.should_answer_passed,
        "wrong_entry_top1": result.wrong_entry_top1,
        "hallucination_risk": result.hallucination_risk,
        "classification": _json_value(result.classification.to_json())
        if result.classification is not None
        else None,
        "proposed_actions": [
            _actionable_action_summary(action) for action in result.proposed_actions
        ],
    }


class RagEvalRepository:
    """Postgres adapter for automatic RAG quality evaluation artifacts.

    Stores generated eval datasets, questions, runs, per-question results and
    final quality reports. This repository deliberately does not call LLMs and
    does not run RAG itself.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def load_document_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalEvidenceEntry]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    re.runtime_entry_id AS id,
                    re.answer AS content,
                    s.document_id::text AS document_id,
                    COALESCE(s.title, re.claim) AS source,
                    'faq_workbench_surface' AS entry_kind,
                    re.claim AS title,
                    re.source_refs,
                    re.question_variants AS questions,
                    '[]'::jsonb AS synonyms,
                    '["faq_workbench", "runtime"]'::jsonb AS tags
                FROM knowledge_workbench_runtime_retrieval_entries AS re
                JOIN knowledge_workbench_surfaces AS s
                  ON s.surface_id = re.surface_id
                WHERE re.project_id = $1::uuid
                  AND s.document_id = $2::uuid
                  AND re.status = 'published'
                  AND re.visibility = 'runtime'
                ORDER BY re.created_at ASC NULLS LAST, re.runtime_entry_id ASC
                """,
                project_id,
                document_id,
            )

        return [self._entry_from_row(row) for row in rows]

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
                        expected_entry_ids,
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
                        expected_entry_ids = EXCLUDED.expected_entry_ids,
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

    async def save_questions(self, *, questions: list[RagEvalQuestion]) -> None:
        if not questions:
            return

        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO rag_eval_questions (
                    id,
                    dataset_id,
                    project_id,
                    document_id,
                    question,
                    question_type,
                    expected_entry_ids,
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
                    expected_entry_ids = EXCLUDED.expected_entry_ids,
                    expected_answer_summary = EXCLUDED.expected_answer_summary,
                    should_answer = EXCLUDED.should_answer,
                    should_escalate = EXCLUDED.should_escalate,
                    difficulty = EXCLUDED.difficulty,
                    severity = EXCLUDED.severity,
                    source = EXCLUDED.source,
                    metadata = EXCLUDED.metadata
                """,
                [self._question_record(question) for question in questions],
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
                    retrieved_entry_ids,
                    top1_hit,
                    top3_hit,
                    top5_hit,
                    expected_entry_found,
                    wrong_entry_top1,
                    answer_text,
                    answer_supported,
                    hallucination_risk,
                    should_answer_passed,
                    score,
                    notes,
                    judge_json,
                    latency_ms,
                    created_at,
                    classification,
                    proposed_actions
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
                    $18,
                    $19::jsonb,
                    $20::jsonb
                )
                ON CONFLICT (id) DO UPDATE SET
                    retrieved_entry_ids = EXCLUDED.retrieved_entry_ids,
                    top1_hit = EXCLUDED.top1_hit,
                    top3_hit = EXCLUDED.top3_hit,
                    top5_hit = EXCLUDED.top5_hit,
                    expected_entry_found = EXCLUDED.expected_entry_found,
                    wrong_entry_top1 = EXCLUDED.wrong_entry_top1,
                    answer_text = EXCLUDED.answer_text,
                    answer_supported = EXCLUDED.answer_supported,
                    hallucination_risk = EXCLUDED.hallucination_risk,
                    should_answer_passed = EXCLUDED.should_answer_passed,
                    score = EXCLUDED.score,
                    notes = EXCLUDED.notes,
                    judge_json = EXCLUDED.judge_json,
                    latency_ms = EXCLUDED.latency_ms,
                    classification = EXCLUDED.classification,
                    proposed_actions = EXCLUDED.proposed_actions
                """,
                result.id,
                result.run_id,
                result.question_id,
                _jsonb([entry.id for entry in result.retrieved_entries]),
                result.top1_hit,
                result.top3_hit,
                result.top5_hit,
                result.expected_entry_found,
                result.wrong_entry_top1,
                result.answer_text,
                result.answer_supported,
                result.hallucination_risk,
                result.should_answer_passed,
                result.score,
                result.notes,
                _jsonb(result.judge_json),
                result.latency_ms,
                result.created_at,
                _optional_jsonb(
                    result.classification.to_json()
                    if result.classification is not None
                    else None
                ),
                _jsonb([action.to_json() for action in result.proposed_actions]),
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

        run_id = str(row["id"])
        run_results = await self.load_run_results(run_id=run_id)

        return {
            "id": run_id,
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
            "results": [_result_summary(result) for result in run_results],
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
                    expected_entry_ids,
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
                    rr.retrieved_entry_ids,
                    rr.top1_hit,
                    rr.top3_hit,
                    rr.top5_hit,
                    rr.expected_entry_found,
                    rr.wrong_entry_top1,
                    rr.classification,
                    rr.proposed_actions,
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
                    q.expected_entry_ids AS q_expected_entry_ids,
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

        run_id = str(row["run_id"])
        run_results = await self.load_run_results(run_id=run_id)

        return {
            "id": str(row["id"]),
            "run_id": run_id,
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
            "actionable_results": [
                _actionable_result_summary(result)
                for result in run_results
                if _is_actionable_result(result)
            ],
        }

    async def get_run_summary(self, *, run_id: str) -> JsonObject | None:
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
                WHERE r.id = $1
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
                """,
                run_id,
            )

        if row is None:
            return None
        return self._run_summary_from_row(row)

    async def load_question_reviews(self, *, run_id: str) -> dict[str, JsonObject]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    question_id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    original_question,
                    edited_question,
                    review_reason,
                    reviewed_by,
                    reviewed_at,
                    created_at,
                    updated_at
                FROM rag_eval_question_reviews
                WHERE run_id = $1
                """,
                run_id,
            )
        return {
            str(row["question_id"]): self._question_review_from_row(row) for row in rows
        }

    async def upsert_question_review(
        self,
        *,
        question_id: str,
        status: str,
        reason: str,
        reviewed_by: str,
    ) -> JsonObject | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                WITH source AS (
                    SELECT
                        q.id AS question_id,
                        rr.run_id,
                        q.dataset_id,
                        q.project_id,
                        q.document_id,
                        COALESCE(q.metadata->>'source_chunk_id', q.expected_entry_ids->>0) AS source_chunk_id,
                        q.question AS original_question
                    FROM rag_eval_questions AS q
                    JOIN rag_eval_results AS rr ON rr.question_id = q.id
                    WHERE q.id = $1
                    ORDER BY rr.created_at DESC
                    LIMIT 1
                )
                INSERT INTO rag_eval_question_reviews (
                    id,
                    question_id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    original_question,
                    review_reason,
                    reviewed_by,
                    reviewed_at
                )
                SELECT
                    'rqrev_' || replace(source.question_id, '-', '_'),
                    source.question_id,
                    source.run_id,
                    source.dataset_id,
                    source.project_id,
                    source.document_id,
                    source.source_chunk_id,
                    $2,
                    source.original_question,
                    $3,
                    $4,
                    now()
                FROM source
                ON CONFLICT (question_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    review_reason = EXCLUDED.review_reason,
                    reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at,
                    updated_at = now()
                RETURNING
                    id,
                    question_id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    original_question,
                    edited_question,
                    review_reason,
                    reviewed_by,
                    reviewed_at,
                    created_at,
                    updated_at
                """,
                question_id,
                status,
                reason,
                reviewed_by,
            )
        return self._question_review_from_row(row) if row is not None else None

    async def edit_question_review(
        self,
        *,
        question_id: str,
        question: str,
        reviewed_by: str,
    ) -> JsonObject | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                WITH source AS (
                    SELECT
                        q.id AS question_id,
                        rr.run_id,
                        q.dataset_id,
                        q.project_id,
                        q.document_id,
                        COALESCE(q.metadata->>'source_chunk_id', q.expected_entry_ids->>0) AS source_chunk_id,
                        q.question AS original_question
                    FROM rag_eval_questions AS q
                    JOIN rag_eval_results AS rr ON rr.question_id = q.id
                    WHERE q.id = $1
                    ORDER BY rr.created_at DESC
                    LIMIT 1
                )
                INSERT INTO rag_eval_question_reviews (
                    id,
                    question_id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    original_question,
                    edited_question,
                    reviewed_by,
                    reviewed_at
                )
                SELECT
                    'rqrev_' || replace(source.question_id, '-', '_'),
                    source.question_id,
                    source.run_id,
                    source.dataset_id,
                    source.project_id,
                    source.document_id,
                    source.source_chunk_id,
                    'edited',
                    source.original_question,
                    $2,
                    $3,
                    now()
                FROM source
                ON CONFLICT (question_id) DO UPDATE SET
                    status = 'edited',
                    edited_question = EXCLUDED.edited_question,
                    reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at,
                    updated_at = now()
                RETURNING
                    id,
                    question_id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    original_question,
                    edited_question,
                    review_reason,
                    reviewed_by,
                    reviewed_at,
                    created_at,
                    updated_at
                """,
                question_id,
                question,
                reviewed_by,
            )
        return self._question_review_from_row(row) if row is not None else None

    async def load_accepted_question_reviews(self, *, run_id: str) -> list[JsonObject]:
        reviews = await self.load_question_reviews(run_id=run_id)
        results = await self.load_run_results(run_id=run_id)
        accepted: list[JsonObject] = []
        for result in results:
            review = reviews.get(result.question_id)
            if review is None or review.get("status") not in {"accepted", "edited"}:
                continue
            target_entry_id = (
                result.question.expected_entry_ids[0]
                if result.question.expected_entry_ids
                else ""
            )
            if not target_entry_id:
                continue
            edited = str(review.get("edited_question") or "").strip()
            accepted.append(
                {
                    "review_id": str(review["id"]),
                    "question_id": result.question_id,
                    "result_id": result.id,
                    "run_id": result.run_id,
                    "dataset_id": result.question.dataset_id,
                    "project_id": result.question.project_id,
                    "document_id": result.question.document_id,
                    "target_entry_id": target_entry_id,
                    "question": edited or result.question.question,
                    "status": str(review["status"]),
                }
            )
        return accepted

    async def mark_question_reviews_applied(
        self, *, review_ids: list[str], reviewed_by: str
    ) -> None:
        if not review_ids:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE rag_eval_question_reviews
                SET status = 'applied',
                    reviewed_by = $2,
                    reviewed_at = now(),
                    updated_at = now()
                WHERE id = ANY($1::text[])
                """,
                review_ids,
                reviewed_by,
            )

    def _run_summary_from_row(self, row: Mapping[str, object]) -> JsonObject:
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
            "result_count": _row_int_value(row, "result_count", 0),
        }

    def _question_review_from_row(self, row: Mapping[str, object]) -> JsonObject:
        reviewed_at = row.get("reviewed_at")
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        return {
            "id": str(row["id"]),
            "question_id": str(row["question_id"]),
            "run_id": str(row["run_id"]),
            "dataset_id": str(row["dataset_id"]),
            "project_id": str(row["project_id"]),
            "document_id": str(row["document_id"]),
            "source_chunk_id": str(row.get("source_chunk_id") or ""),
            "status": str(row["status"]),
            "original_question": str(row["original_question"] or ""),
            "edited_question": str(row.get("edited_question") or ""),
            "review_reason": str(row.get("review_reason") or ""),
            "reviewed_by": str(row.get("reviewed_by") or ""),
            "reviewed_at": reviewed_at.isoformat()
            if hasattr(reviewed_at, "isoformat")
            else None,
            "created_at": created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else str(created_at),
            "updated_at": updated_at.isoformat()
            if hasattr(updated_at, "isoformat")
            else str(updated_at),
        }

    async def upsert_review_group(
        self,
        *,
        run_id: str,
        dataset_id: str,
        project_id: str,
        document_id: str,
        source_chunk_id: str,
        status: str,
        questions_total: int = 0,
        checked_questions: int = 0,
        reliable_count: int = 0,
        weak_count: int = 0,
        confused_count: int = 0,
        missing_count: int = 0,
        improvement_count: int = 0,
        review_payload: Mapping[str, object] | None = None,
        error: str = "",
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_eval_review_groups (
                    id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    questions_total,
                    checked_questions,
                    reliable_count,
                    weak_count,
                    confused_count,
                    missing_count,
                    improvement_count,
                    review_payload_json,
                    error
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4::uuid,
                    $5::uuid,
                    $6,
                    $7,
                    $8,
                    $9,
                    $10,
                    $11,
                    $12,
                    $13,
                    $14,
                    $15::jsonb,
                    $16
                )
                ON CONFLICT (run_id, source_chunk_id) DO UPDATE SET
                    dataset_id = EXCLUDED.dataset_id,
                    project_id = EXCLUDED.project_id,
                    document_id = EXCLUDED.document_id,
                    status = EXCLUDED.status,
                    questions_total = EXCLUDED.questions_total,
                    checked_questions = EXCLUDED.checked_questions,
                    reliable_count = EXCLUDED.reliable_count,
                    weak_count = EXCLUDED.weak_count,
                    confused_count = EXCLUDED.confused_count,
                    missing_count = EXCLUDED.missing_count,
                    improvement_count = EXCLUDED.improvement_count,
                    review_payload_json = EXCLUDED.review_payload_json,
                    error = EXCLUDED.error,
                    updated_at = now()
                """,
                f"rgrev_{run_id}_{source_chunk_id}"[:180],
                run_id,
                dataset_id,
                project_id,
                document_id,
                source_chunk_id,
                status,
                questions_total,
                checked_questions,
                reliable_count,
                weak_count,
                confused_count,
                missing_count,
                improvement_count,
                _jsonb(review_payload or {}),
                error,
            )

    async def load_review_group_projections(self, *, run_id: str) -> list[JsonObject]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    run_id,
                    dataset_id,
                    project_id,
                    document_id,
                    source_chunk_id,
                    status,
                    questions_total,
                    checked_questions,
                    reliable_count,
                    weak_count,
                    confused_count,
                    missing_count,
                    improvement_count,
                    review_payload_json,
                    error,
                    created_at,
                    updated_at
                FROM rag_eval_review_groups
                WHERE run_id = $1
                ORDER BY updated_at DESC, source_chunk_id ASC
                """,
                run_id,
            )

        projections: list[JsonObject] = []
        for row in rows:
            projections.append(
                {
                    "id": str(row["id"]),
                    "run_id": str(row["run_id"]),
                    "dataset_id": str(row["dataset_id"]),
                    "project_id": str(row["project_id"]),
                    "document_id": str(row["document_id"]),
                    "source_chunk_id": str(row["source_chunk_id"]),
                    "status": str(row["status"]),
                    "questions_total": _row_int_value(row, "questions_total", 0),
                    "checked_questions": _row_int_value(row, "checked_questions", 0),
                    "reliable_count": _row_int_value(row, "reliable_count", 0),
                    "weak_count": _row_int_value(row, "weak_count", 0),
                    "confused_count": _row_int_value(row, "confused_count", 0),
                    "missing_count": _row_int_value(row, "missing_count", 0),
                    "improvement_count": _row_int_value(row, "improvement_count", 0),
                    "review_payload": cast(
                        JsonObject, _json_object(row.get("review_payload_json"))
                    ),
                    "error": str(row["error"] or ""),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                }
            )
        return projections

    def _entry_from_row(self, row: Mapping[str, object]) -> RagEvalEvidenceEntry:
        source_refs = _source_ref_views_from_payload(row.get("source_refs"))
        source_excerpt = source_refs[0].quote if source_refs else ""
        return RagEvalEvidenceEntry(
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
                "questions": row.get("questions"),
                "synonyms": row.get("synonyms"),
                "tags": row.get("tags"),
            },
        )

    def _question_from_row(self, row: Mapping[str, object]) -> RagEvalQuestion:
        expected_entry_ids = [
            str(item)
            for item in _json_list(row.get("expected_entry_ids"))
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
            expected_entry_ids=expected_entry_ids,
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
        expected_entry_ids = [
            str(item)
            for item in _json_list(row.get("q_expected_entry_ids"))
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
            expected_entry_ids=expected_entry_ids,
            expected_answer_summary=str(row["q_expected_answer_summary"] or ""),
            should_answer=bool(row["q_should_answer"]),
            should_escalate=bool(row["q_should_escalate"]),
            difficulty=_row_int_value(row, "q_difficulty", 1),
            severity=cast(RagEvalSeverity, str(row["q_severity"] or "medium")),
            source=str(row["q_source"] or "llm_generated"),
            metadata=_json_object(row.get("q_metadata")),
            created_at=_row_datetime_value(row, "q_created_at"),
        )

    async def load_result_action_source(self, result_id: str) -> JsonObject | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    rr.id,
                    rr.run_id,
                    rr.question_id,
                    rr.proposed_actions,
                    q.project_id,
                    q.document_id,
                    q.question
                FROM rag_eval_results AS rr
                JOIN rag_eval_questions AS q ON q.id = rr.question_id
                WHERE rr.id = $1
                """,
                result_id,
            )

        if row is None:
            return None

        return {
            "id": str(row["id"]),
            "run_id": str(row["run_id"]),
            "question_id": str(row["question_id"]),
            "project_id": str(row["project_id"]),
            "document_id": str(row["document_id"]),
            "question": str(row["question"]),
            "proposed_actions": row["proposed_actions"],
        }

    def _result_from_joined_row(self, row: Mapping[str, object]) -> RagEvalResult:
        return RagEvalResult(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            question_id=str(row["question_id"]),
            question=self._question_from_joined_result_row(row),
            retrieved_entries=[],
            answer_text=str(row["answer_text"] or ""),
            top1_hit=bool(row["top1_hit"]),
            top3_hit=bool(row["top3_hit"]),
            top5_hit=bool(row["top5_hit"]),
            expected_entry_found=bool(row["expected_entry_found"]),
            wrong_entry_top1=bool(row["wrong_entry_top1"]),
            classification=failure_classification_from_mapping(
                row.get("classification")
            ),
            proposed_actions=knowledge_edit_actions_from_value(
                row.get("proposed_actions")
            ),
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
            _jsonb(question.expected_entry_ids),
            question.expected_answer_summary,
            question.should_answer,
            question.should_escalate,
            question.difficulty,
            question.severity,
            question.source,
            _jsonb(question.metadata),
            question.created_at,
        )
