from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, cast

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionCandidateDetails,
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRetrievalResultDetails,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalPromotionStatus,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)


PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL = """
SELECT
    entry.runtime_entry_id,
    CASE
        WHEN entry.source_refs ? 'workflow_run_id'
        THEN 'draft-claim-curation-publication:' || (entry.source_refs->>'workflow_run_id')
        ELSE NULL
    END AS publication_id,
    entry.project_id::text AS project_id,
    entry.source_refs->>'source_document_ref' AS source_document_ref,
    entry.fact_id,
    entry.source_refs->>'curation_item_ref' AS curation_item_ref,
    entry.claim,
    entry.possible_questions,
    fact.exclusion_scope,
    NULL::text AS evidence_block,
    entry.source_refs,
    entry.source_refs->'source_claim_refs' AS source_claim_refs,
    entry.embedding_text,
    1.0::double precision AS score,
    row_number() OVER (ORDER BY entry.created_at, entry.runtime_entry_id) AS rank
FROM knowledge_workbench_runtime_retrieval_entries AS entry
JOIN knowledge_workbench_canonical_facts AS fact
  ON fact.fact_id = entry.fact_id
WHERE entry.project_id = $1::uuid
  AND entry.visibility = 'published'
  AND entry.status = 'active'
  AND fact.status = 'published'
  AND ($2::text IS NULL OR (
        entry.source_refs ? 'workflow_run_id'
        AND 'draft-claim-curation-publication:' || (entry.source_refs->>'workflow_run_id') = $2
      ))
  AND ($3::text IS NULL OR entry.source_refs->>'source_document_ref' = $3)
ORDER BY entry.created_at, entry.runtime_entry_id
LIMIT $4
"""


WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL = """
SELECT
    question.question_id,
    question.run_id,
    question.project_id::text AS project_id,
    question.expected_runtime_entry_id,
    question.expected_fact_id,
    question.question,
    question.question_kind,
    question.source,
    question.generation_model,
    question.prompt_version,
    question.status,
    question.created_at,
    result.result_id,
    result.matched_runtime_entry_id,
    result.matched_fact_id,
    result.rank,
    result.score,
    result.top1_hit,
    result.top3_hit,
    result.top5_hit,
    result.created_at AS result_created_at
FROM knowledge_workbench_rag_eval_questions AS question
LEFT JOIN knowledge_workbench_rag_eval_retrieval_results AS result
  ON result.question_id = question.question_id
 AND result.run_id = question.run_id
 AND result.project_id = question.project_id
WHERE question.project_id = $1::uuid
  AND question.run_id = $2
ORDER BY question.created_at, question.question_id, result.rank NULLS LAST, result.created_at
"""


WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL = """
SELECT
    promotion_id,
    run_id,
    question_id,
    project_id::text AS project_id,
    target_runtime_entry_id,
    target_fact_id,
    question,
    status,
    created_at,
    applied_at
FROM knowledge_workbench_rag_eval_promoted_questions
WHERE project_id = $1::uuid
  AND run_id = $2
ORDER BY created_at, promotion_id
"""


WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_BY_ID_SQL = """
SELECT
    promotion_id,
    run_id,
    question_id,
    project_id::text AS project_id,
    target_runtime_entry_id,
    target_fact_id,
    question,
    status,
    created_at,
    applied_at
FROM knowledge_workbench_rag_eval_promoted_questions
WHERE project_id = $1::uuid
  AND promotion_id = $2
"""


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL = """
SELECT
    promotion.promotion_id,
    promotion.run_id,
    promotion.question_id,
    promotion.project_id::text AS project_id,
    promotion.target_runtime_entry_id,
    promotion.target_fact_id,
    promotion.question,
    promotion.status,
    promotion.created_at,
    promotion.applied_at,
    entry.claim,
    entry.possible_questions AS runtime_possible_questions,
    entry.embedding_text AS existing_embedding_text,
    fact.possible_questions AS fact_possible_questions,
    fact.exclusion_scope
FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
JOIN knowledge_workbench_runtime_retrieval_entries AS entry
  ON entry.runtime_entry_id = promotion.target_runtime_entry_id
 AND entry.project_id = promotion.project_id
JOIN knowledge_workbench_canonical_facts AS fact
  ON fact.fact_id = promotion.target_fact_id
 AND fact.project_id = promotion.project_id
WHERE promotion.project_id = $1::uuid
  AND promotion.promotion_id = $2
  AND entry.visibility = 'published'
  AND entry.status = 'active'
  AND fact.status = 'published'
"""


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_FOR_UPDATE_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL
    + " FOR UPDATE OF promotion, entry, fact"
)


class WorkbenchRagEvalTransactionLike(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None: ...


class WorkbenchRagEvalConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> object: ...

    def transaction(self) -> WorkbenchRagEvalTransactionLike: ...

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...

    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...


class WorkbenchRagEvalAcquireContextLike(Protocol):
    async def __aenter__(self) -> WorkbenchRagEvalConnectionLike: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None: ...


class WorkbenchRagEvalPoolLike(Protocol):
    def acquire(self) -> WorkbenchRagEvalAcquireContextLike: ...


class PostgresWorkbenchRagEvalRepository(WorkbenchRagEvalRepositoryPort):
    def __init__(self, connection_or_pool: object) -> None:
        self._connection_or_pool = connection_or_pool

    async def create_run(self, *, run: WorkbenchRagEvalRun) -> WorkbenchRagEvalRun:
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """
                INSERT INTO knowledge_workbench_rag_eval_runs (
                    run_id, project_id, publication_id, source_document_ref,
                    status, question_generation_model,
                    question_generation_prompt_version, total_entries,
                    total_questions, completed_questions, top1_hits,
                    top3_hits, top5_hits, misses, created_at, started_at,
                    completed_at, error_message
                )
                VALUES (
                    $1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18
                )
                """,
                run.run_id,
                run.project_id,
                run.publication_id,
                run.source_document_ref,
                run.status.value,
                run.question_generation_model,
                run.question_generation_prompt_version,
                run.total_entries,
                run.total_questions,
                run.completed_questions,
                run.top1_hits,
                run.top3_hits,
                run.top5_hits,
                run.misses,
                run.created_at,
                run.started_at,
                run.completed_at,
                run.error_message,
            )
        return run

    async def list_published_entries_for_eval(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        limit: int,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL,
                project_id,
                publication_id,
                source_document_ref,
                limit,
            )
        return tuple(_published_entry_from_row(row) for row in rows)

    async def save_generated_questions(
        self,
        *,
        questions: tuple[WorkbenchRagEvalQuestion, ...],
    ) -> tuple[WorkbenchRagEvalQuestion, ...]:
        async with _connection(self._connection_or_pool) as connection:
            for question in questions:
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_questions (
                        question_id, run_id, project_id,
                        expected_runtime_entry_id, expected_fact_id, question,
                        question_kind, source, generation_model, prompt_version,
                        status, created_at
                    )
                    VALUES ($1, $2, $3::uuid, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (question_id) DO NOTHING
                    """,
                    question.question_id,
                    question.run_id,
                    question.project_id,
                    question.expected_runtime_entry_id,
                    question.expected_fact_id,
                    question.question,
                    question.question_kind.value,
                    question.source.value,
                    question.generation_model,
                    question.prompt_version,
                    question.status.value,
                    question.created_at,
                )
        return questions

    async def save_retrieval_results(
        self,
        *,
        results: tuple[WorkbenchRagEvalRetrievalResult, ...],
    ) -> tuple[WorkbenchRagEvalRetrievalResult, ...]:
        async with _connection(self._connection_or_pool) as connection:
            for result in results:
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_retrieval_results (
                        result_id, run_id, question_id, project_id,
                        expected_runtime_entry_id, matched_runtime_entry_id,
                        matched_fact_id, rank, score, top1_hit, top3_hit,
                        top5_hit, created_at
                    )
                    VALUES ($1, $2, $3, $4::uuid, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (result_id) DO NOTHING
                    """,
                    result.result_id,
                    result.run_id,
                    result.question_id,
                    result.project_id,
                    result.expected_runtime_entry_id,
                    result.matched_runtime_entry_id,
                    result.matched_fact_id,
                    result.rank,
                    result.score,
                    result.top1_hit,
                    result.top3_hit,
                    result.top5_hit,
                    result.created_at,
                )
        return results

    async def save_promoted_question_candidates(
        self,
        *,
        promotions: tuple[WorkbenchRagEvalPromotedQuestion, ...],
    ) -> tuple[WorkbenchRagEvalPromotedQuestion, ...]:
        async with _connection(self._connection_or_pool) as connection:
            for promotion in promotions:
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_promoted_questions (
                        promotion_id, run_id, question_id, project_id,
                        target_runtime_entry_id, target_fact_id, question,
                        status, created_at, applied_at
                    )
                    VALUES ($1, $2, $3, $4::uuid, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (promotion_id) DO NOTHING
                    """,
                    promotion.promotion_id,
                    promotion.run_id,
                    promotion.question_id,
                    promotion.project_id,
                    promotion.target_runtime_entry_id,
                    promotion.target_fact_id,
                    promotion.question,
                    promotion.status.value,
                    promotion.created_at,
                    promotion.applied_at,
                )
        return promotions

    async def complete_run(
        self,
        *,
        summary: WorkbenchRagEvalSummary,
    ) -> WorkbenchRagEvalSummary:
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """
                UPDATE knowledge_workbench_rag_eval_runs
                SET status = $2,
                    total_entries = $3,
                    total_questions = $4,
                    completed_questions = $5,
                    top1_hits = $6,
                    top3_hits = $7,
                    top5_hits = $8,
                    misses = $9,
                    completed_at = $10,
                    error_message = $11
                WHERE run_id = $1
                """,
                summary.run_id,
                summary.status.value,
                summary.total_entries,
                summary.total_questions,
                summary.completed_questions,
                summary.top1_hits,
                summary.top3_hits,
                summary.top5_hits,
                summary.misses,
                summary.completed_at,
                summary.error_message,
            )
        return summary

    async def get_latest_run(
        self,
        *,
        project_id: str,
    ) -> WorkbenchRagEvalSummary | None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    run.*,
                    (
                        SELECT count(*)
                        FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
                        WHERE promotion.run_id = run.run_id
                          AND promotion.status = 'candidate'
                    ) AS promotion_candidate_count
                FROM knowledge_workbench_rag_eval_runs AS run
                WHERE run.project_id = $1::uuid
                ORDER BY run.created_at DESC
                LIMIT 1
                """,
                project_id,
            )
        return _summary_from_row(row) if row is not None else None

    async def get_run(
        self,
        *,
        run_id: str,
        project_id: str,
    ) -> WorkbenchRagEvalSummary | None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    run.*,
                    (
                        SELECT count(*)
                        FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
                        WHERE promotion.run_id = run.run_id
                          AND promotion.status = 'candidate'
                    ) AS promotion_candidate_count
                FROM knowledge_workbench_rag_eval_runs AS run
                WHERE run.run_id = $1
                  AND run.project_id = $2::uuid
                """,
                run_id,
                project_id,
            )
        return _summary_from_row(row) if row is not None else None

    async def list_run_questions(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> tuple[WorkbenchRagEvalQuestionDetails, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL,
                project_id,
                run_id,
            )
        return _question_details_from_rows(rows)

    async def list_run_promotion_candidates(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> tuple[WorkbenchRagEvalPromotionCandidateDetails, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL,
                project_id,
                run_id,
            )
        return tuple(_promotion_candidate_from_row(row) for row in rows)

    async def get_promotion_candidate(
        self,
        *,
        project_id: str,
        promotion_id: str,
    ) -> WorkbenchRagEvalPromotionCandidateDetails | None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_BY_ID_SQL,
                project_id,
                promotion_id,
            )
        return _promotion_candidate_from_row(row) if row is not None else None

    async def get_promotion_application_target(
        self,
        *,
        project_id: str,
        promotion_id: str,
    ) -> WorkbenchRagEvalPromotionApplicationTarget | None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL,
                project_id,
                promotion_id,
            )
        return _promotion_application_target_from_row(row) if row is not None else None

    async def apply_promotion_candidate(
        self,
        *,
        project_id: str,
        promotion_id: str,
        embedding_model_id: str,
        dimensions: int,
        embedding: Sequence[float],
        embedding_text: str,
        embedding_text_hash: str,
        applied_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplyResult:
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_FOR_UPDATE_SQL,
                    project_id,
                    promotion_id,
                )
                if row is None:
                    raise LookupError("Promotion candidate not found")
                target = _promotion_application_target_from_row(row)
                if target.status is WorkbenchRagEvalPromotionStatus.APPLIED:
                    raise RuntimeError("Promotion candidate is already applied")
                if target.status not in (
                    WorkbenchRagEvalPromotionStatus.CANDIDATE,
                    WorkbenchRagEvalPromotionStatus.ACCEPTED,
                ):
                    raise RuntimeError(
                        "Promotion candidate status cannot be applied: "
                        f"{target.status.value}"
                    )

                runtime_questions = _append_text_once(
                    target.runtime_possible_questions,
                    target.question,
                )
                fact_questions = _append_text_once(
                    target.fact_possible_questions,
                    target.question,
                )

                await connection.execute(
                    """
                    UPDATE knowledge_workbench_canonical_facts
                    SET possible_questions = $3::jsonb,
                        updated_at = $4
                    WHERE project_id = $1::uuid
                      AND fact_id = $2
                    """,
                    project_id,
                    target.target_fact_id,
                    _json_text_list(fact_questions),
                    applied_at,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_workbench_runtime_retrieval_entries
                    SET possible_questions = $3::jsonb,
                        embedding_text = $4
                    WHERE project_id = $1::uuid
                      AND runtime_entry_id = $2
                    """,
                    project_id,
                    target.target_runtime_entry_id,
                    _json_text_list(runtime_questions),
                    embedding_text,
                )
                await connection.execute(
                    """
                    DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
                    WHERE runtime_entry_id = $1
                      AND embedding_model_id = $2
                    """,
                    target.target_runtime_entry_id,
                    embedding_model_id,
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings (
                        runtime_entry_id, embedding_model_id, dimensions,
                        embedding, embedding_text_hash, created_at
                    )
                    VALUES ($1, $2, $3, $4::vector, $5, $6)
                    """,
                    target.target_runtime_entry_id,
                    embedding_model_id,
                    dimensions,
                    _pg_vector_text(tuple(float(value) for value in embedding)),
                    embedding_text_hash,
                    applied_at,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_promoted_questions
                    SET status = 'applied',
                        applied_at = $3
                    WHERE project_id = $1::uuid
                      AND promotion_id = $2
                    """,
                    project_id,
                    promotion_id,
                    applied_at,
                )

        return WorkbenchRagEvalPromotionApplyResult(
            promotion_id=target.promotion_id,
            run_id=target.run_id,
            question_id=target.question_id,
            project_id=target.project_id,
            target_runtime_entry_id=target.target_runtime_entry_id,
            target_fact_id=target.target_fact_id,
            question=target.question,
            status=WorkbenchRagEvalPromotionStatus.APPLIED,
            possible_question_count=len(runtime_questions),
            embedding_model_id=embedding_model_id,
            embedding_count=1,
            applied_at=applied_at,
        )


class _DirectConnectionContext:
    def __init__(self, connection: WorkbenchRagEvalConnectionLike) -> None:
        self._connection = connection

    async def __aenter__(self) -> WorkbenchRagEvalConnectionLike:
        return self._connection

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None:
        return None


def _connection(connection_or_pool: object):
    acquire = getattr(connection_or_pool, "acquire", None)
    if callable(acquire):
        return cast(WorkbenchRagEvalPoolLike, connection_or_pool).acquire()
    return _DirectConnectionContext(
        cast(WorkbenchRagEvalConnectionLike, connection_or_pool)
    )


@dataclass(slots=True)
class _QuestionDetailsDraft:
    question_id: str
    run_id: str
    project_id: str
    expected_runtime_entry_id: str
    expected_fact_id: str
    question: str
    question_kind: WorkbenchRagEvalQuestionKind
    source: WorkbenchRagEvalQuestionSource
    generation_model: str | None
    prompt_version: str | None
    status: WorkbenchRagEvalQuestionStatus
    created_at: datetime
    results: list[WorkbenchRagEvalRetrievalResultDetails] = field(default_factory=list)

    def to_details(self) -> WorkbenchRagEvalQuestionDetails:
        return WorkbenchRagEvalQuestionDetails(
            question_id=self.question_id,
            run_id=self.run_id,
            project_id=self.project_id,
            expected_runtime_entry_id=self.expected_runtime_entry_id,
            expected_fact_id=self.expected_fact_id,
            question=self.question,
            question_kind=self.question_kind,
            source=self.source,
            generation_model=self.generation_model,
            prompt_version=self.prompt_version,
            status=self.status,
            created_at=self.created_at,
            results=tuple(self.results),
        )


def _question_details_from_rows(
    rows: list[Mapping[str, object]],
) -> tuple[WorkbenchRagEvalQuestionDetails, ...]:
    drafts: dict[str, _QuestionDetailsDraft] = {}
    order: list[str] = []
    for row in rows:
        question_id = _text_from_row(row, "question_id")
        draft = drafts.get(question_id)
        if draft is None:
            draft = _QuestionDetailsDraft(
                question_id=question_id,
                run_id=_text_from_row(row, "run_id"),
                project_id=_text_from_row(row, "project_id"),
                expected_runtime_entry_id=_text_from_row(
                    row, "expected_runtime_entry_id"
                ),
                expected_fact_id=_text_from_row(row, "expected_fact_id"),
                question=_text_from_row(row, "question"),
                question_kind=WorkbenchRagEvalQuestionKind(
                    _text_from_row(row, "question_kind")
                ),
                source=WorkbenchRagEvalQuestionSource(_text_from_row(row, "source")),
                generation_model=_optional_text_from_row(row, "generation_model"),
                prompt_version=_optional_text_from_row(row, "prompt_version"),
                status=WorkbenchRagEvalQuestionStatus(_text_from_row(row, "status")),
                created_at=_datetime_from_row(row, "created_at"),
            )
            drafts[question_id] = draft
            order.append(question_id)

        if row.get("result_id") is not None:
            draft.results.append(_result_details_from_row(row))

    return tuple(drafts[question_id].to_details() for question_id in order)


def _result_details_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalRetrievalResultDetails:
    return WorkbenchRagEvalRetrievalResultDetails(
        result_id=_text_from_row(row, "result_id"),
        matched_runtime_entry_id=_text_from_row(row, "matched_runtime_entry_id"),
        matched_fact_id=_text_from_row(row, "matched_fact_id"),
        rank=_int_from_row(row, "rank"),
        score=_float_from_row(row, "score"),
        top1_hit=_bool_from_row(row, "top1_hit"),
        top3_hit=_bool_from_row(row, "top3_hit"),
        top5_hit=_bool_from_row(row, "top5_hit"),
        created_at=_datetime_from_row(row, "result_created_at"),
    )


def _promotion_application_target_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalPromotionApplicationTarget:
    return WorkbenchRagEvalPromotionApplicationTarget(
        promotion_id=_text_from_row(row, "promotion_id"),
        run_id=_text_from_row(row, "run_id"),
        question_id=_text_from_row(row, "question_id"),
        project_id=_text_from_row(row, "project_id"),
        target_runtime_entry_id=_text_from_row(row, "target_runtime_entry_id"),
        target_fact_id=_text_from_row(row, "target_fact_id"),
        question=_text_from_row(row, "question"),
        status=WorkbenchRagEvalPromotionStatus(_text_from_row(row, "status")),
        claim=_text_from_row(row, "claim"),
        runtime_possible_questions=_text_tuple(row.get("runtime_possible_questions")),
        fact_possible_questions=_text_tuple(row.get("fact_possible_questions")),
        exclusion_scope=_optional_text_from_row(row, "exclusion_scope"),
        existing_embedding_text=_text_from_row(row, "existing_embedding_text"),
    )


def _promotion_candidate_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalPromotionCandidateDetails:
    return WorkbenchRagEvalPromotionCandidateDetails(
        promotion_id=_text_from_row(row, "promotion_id"),
        run_id=_text_from_row(row, "run_id"),
        question_id=_text_from_row(row, "question_id"),
        project_id=_text_from_row(row, "project_id"),
        target_runtime_entry_id=_text_from_row(row, "target_runtime_entry_id"),
        target_fact_id=_text_from_row(row, "target_fact_id"),
        question=_text_from_row(row, "question"),
        status=WorkbenchRagEvalPromotionStatus(_text_from_row(row, "status")),
        created_at=_datetime_from_row(row, "created_at"),
        applied_at=_optional_datetime_from_row(row, "applied_at"),
    )


def _published_entry_from_row(
    row: Mapping[str, object],
) -> PublishedWorkbenchRetrievalResult:
    source_ref = PublishedWorkbenchRetrievalSourceRef(
        workflow_run_id=_optional_text_from_row(row, "workflow_run_id"),
        source_document_ref=_optional_text_from_row(row, "source_document_ref"),
        curation_item_ref=_optional_text_from_row(row, "curation_item_ref"),
        source_claim_refs=_text_tuple(row.get("source_claim_refs")),
    )
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id=_text_from_row(row, "runtime_entry_id"),
        publication_id=_optional_text_from_row(row, "publication_id"),
        project_id=_text_from_row(row, "project_id"),
        source_document_ref=source_ref.source_document_ref,
        fact_id=_text_from_row(row, "fact_id"),
        curation_item_ref=source_ref.curation_item_ref,
        claim=_text_from_row(row, "claim"),
        possible_questions=_text_tuple(row.get("possible_questions")),
        exclusion_scope=_optional_text_from_row(row, "exclusion_scope"),
        evidence_block=_optional_text_from_row(row, "evidence_block"),
        source_claim_refs=source_ref.source_claim_refs,
        embedding_text=_text_from_row(row, "embedding_text"),
        score=_float_from_row(row, "score"),
        rank=_int_from_row(row, "rank"),
        source_ref=source_ref,
    )


def _summary_from_row(row: Mapping[str, object]) -> WorkbenchRagEvalSummary:
    return WorkbenchRagEvalSummary(
        run_id=_text_from_row(row, "run_id"),
        project_id=_text_from_row(row, "project_id"),
        publication_id=_optional_text_from_row(row, "publication_id"),
        source_document_ref=_optional_text_from_row(row, "source_document_ref"),
        status=WorkbenchRagEvalRunStatus(_text_from_row(row, "status")),
        total_entries=_int_from_row(row, "total_entries"),
        total_questions=_int_from_row(row, "total_questions"),
        completed_questions=_int_from_row(row, "completed_questions"),
        top1_hits=_int_from_row(row, "top1_hits"),
        top3_hits=_int_from_row(row, "top3_hits"),
        top5_hits=_int_from_row(row, "top5_hits"),
        misses=_int_from_row(row, "misses"),
        promotion_candidate_count=_int_from_row(row, "promotion_candidate_count"),
        created_at=_datetime_from_row(row, "created_at"),
        completed_at=_optional_datetime_from_row(row, "completed_at"),
        error_message=_optional_text_from_row(row, "error_message"),
    )


def _text_from_row(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _optional_text_from_row(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text or None")
    stripped = value.strip()
    return stripped or None


def _append_text_once(
    values: tuple[str, ...],
    value: str,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in (*values, value):
        stripped = item.strip()
        if not stripped:
            continue
        normalized = " ".join(stripped.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(stripped)
    return tuple(result)


def _json_text_list(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(list(values), ensure_ascii=False)


def _pg_vector_text(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError("tuple source must be list")
    return tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )


def _int_from_row(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _float_from_row(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _bool_from_row(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _datetime_from_row(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _optional_datetime_from_row(
    row: Mapping[str, object],
    key: str,
) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime or None")
    return value
