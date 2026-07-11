from __future__ import annotations

from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_text_array_payload,
)
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Protocol, cast

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalAdjudication,
    WorkbenchRagEvalAdjudicationVerdict,
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionCandidateDetails,
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
    WorkbenchRagEvalRetrievalOutcome,
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRetrievalResultDetails,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalPromotionStatus,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_normalization_policy import (
    normalize_workbench_rag_eval_question,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_adjudication_work import (
    WorkbenchRagEvalAdjudicationPlanningInput,
    WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot,
    WorkbenchRagEvalAdjudicationEligibilityPolicy,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)


PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL = """
SELECT
    entry.runtime_entry_id,
    entry.publication_id,
    entry.project_id::text AS project_id,
    entry.source_document_ref,
    COALESCE(NULLIF(entry.fact_id, ''), entry.runtime_entry_id) AS fact_id,
    entry.curation_item_ref,
    entry.claim,
    entry.possible_questions,
    entry.exclusion_scope,
    entry.evidence_block,
    entry.triples,
    entry.source_refs,
    entry.source_claim_refs,
    entry.embedding_text,
    1.0::double precision AS score,
    row_number() OVER (ORDER BY entry.created_at, entry.runtime_entry_id) AS rank
FROM knowledge_workbench_runtime_retrieval_entries AS entry
JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
  ON emb.runtime_entry_id = entry.runtime_entry_id
WHERE entry.project_id = $1::uuid
  AND entry.visibility = 'published'
  AND entry.status = 'active'
  AND ($2::text IS NULL OR entry.publication_id = $2)
  AND ($3::text IS NULL OR entry.source_document_ref = $3)
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
    question.contract_version,
    question.promotion_eligible,
    question.ambiguity_risk,
    question.generation_rationale,
    question.generation_account_ref,
    question.generation_slot_index,
    question.evaluation_role,
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
    entry.possible_questions AS fact_possible_questions,
    entry.exclusion_scope,
    entry.evidence_block,
    entry.triples,
    entry.embedding_text AS existing_embedding_text,
FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
JOIN knowledge_workbench_runtime_retrieval_entries AS entry
  ON entry.runtime_entry_id = promotion.target_runtime_entry_id
 AND entry.project_id = promotion.project_id
WHERE promotion.project_id = $1::uuid
  AND promotion.promotion_id = $2
  AND entry.visibility = 'published'
  AND entry.status = 'active'
"""


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_FOR_UPDATE_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL
    + " FOR UPDATE OF promotion, entry"
)

WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_BY_IDS_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL.replace(
        "promotion.promotion_id = $2",
        "promotion.promotion_id = ANY($2::text[])",
    )
)


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_RUN_SQL = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL.replace(
    "promotion.promotion_id = $2",
    "promotion.run_id = $2 AND promotion.status IN ('candidate', 'accepted', 'applied')",
)


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_UPDATE_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_BY_IDS_SQL
    + " AND promotion.target_runtime_entry_id = $3"
    + " FOR UPDATE OF promotion, entry"
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

    async def materialize_baseline_questions(
        self, *, run_id: str, project_id: str, created_at: datetime
    ) -> int:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                SELECT
                    schedule.payload->>'workflow_run_id' AS run_id,
                    schedule.payload->>'project_id' AS project_id,
                    schedule.payload->>'runtime_entry_id' AS runtime_entry_id,
                    schedule.payload->>'expected_fact_id' AS expected_fact_id,
                    possible.question AS question
                FROM execution_work_item_schedules AS schedule
                JOIN execution_work_items AS item
                  ON item.work_item_id = schedule.work_item_id
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    schedule.payload->'possible_questions'
                ) AS possible(question)
                WHERE item.work_kind = 'workbench_rag_eval.question_generation'
                  AND schedule.payload->>'workflow_run_id' = $1
                  AND schedule.payload->>'project_id' = $2
                ORDER BY schedule.created_at, schedule.work_item_id, possible.question
                """,
                run_id,
                project_id,
            )
            questions = _baseline_questions_from_schedule_rows(
                rows=rows,
                run_id=run_id,
                project_id=project_id,
                created_at=created_at,
            )
            inserted = 0
            for question in questions:
                inserted += int(await _insert_rag_eval_question(connection, question))
            return inserted

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
                    completed_at, error_message, current_phase, blocked_reason,
                    failed_reason, updated_at, selected_entries,
                    scheduled_generation_items, waiting_work_items,
                    running_work_items, completed_work_items, failed_work_items,
                    generated_question_sets, capacity_next_due_at,
                    capacity_model_ref, capacity_account_ref,
                    adjudication_total, adjudication_waiting,
                    adjudication_running, adjudication_completed,
                    adjudication_failed, promotion_candidate_count
                )
                VALUES (
                    $1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                    $21, $22, $23, $24, $25, $26, $27, $28, $29, $30,
                    $31, $32, $33, $34, $35, $36, $37, $38, $39
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
                run.current_phase.value,
                run.blocked_reason,
                run.failed_reason,
                run.updated_at or run.created_at,
                run.progress.selected_entries,
                run.progress.scheduled_generation_items,
                run.progress.waiting,
                run.progress.running,
                run.progress.completed,
                run.progress.failed,
                run.progress.generated_question_sets,
                run.capacity_next_due_at,
                run.capacity_model_ref,
                run.capacity_account_ref,
                run.progress.adjudication_total,
                run.progress.adjudication_waiting,
                run.progress.adjudication_running,
                run.progress.adjudication_completed,
                run.progress.adjudication_failed,
                run.progress.promotion_candidate_count,
            )
        return run

    async def has_complete_question_sets(
        self,
        *,
        rag_eval_run_id: str,
        expected_entry_count: int,
        questions_per_entry: int,
    ) -> bool:
        if expected_entry_count <= 0 or questions_per_entry <= 0:
            return False

        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                """
                WITH generated_per_entry AS (
                    SELECT
                        expected_runtime_entry_id,
                        COUNT(*) AS question_count
                    FROM knowledge_workbench_rag_eval_questions
                    WHERE run_id = $1
                      AND source = 'generated'
                    GROUP BY expected_runtime_entry_id
                )
                SELECT
                    COALESCE(
                        SUM(question_count),
                        0
                    ) AS total_questions,
                    COUNT(*) AS represented_entry_count,
                    COUNT(*) FILTER (
                        WHERE question_count = $2
                    ) AS complete_entry_count,
                    COUNT(*) FILTER (
                        WHERE question_count <> $2
                    ) AS incomplete_entry_count
                FROM generated_per_entry
                """,
                rag_eval_run_id,
                questions_per_entry,
            )

        if row is None:
            return False

        return (
            _int_from_row(row, "total_questions")
            == expected_entry_count * questions_per_entry
            and _int_from_row(row, "represented_entry_count") == expected_entry_count
            and _int_from_row(row, "complete_entry_count") == expected_entry_count
            and _int_from_row(row, "incomplete_entry_count") == 0
        )

    async def transition_run_progress(
        self,
        *,
        run_id: str,
        project_id: str,
        status: WorkbenchRagEvalRunStatus,
        current_phase: WorkbenchRagEvalCurrentPhase,
        progress: WorkbenchRagEvalRunProgress,
        updated_at: datetime,
        blocked_reason: str | None = None,
        failed_reason: str | None = None,
        capacity_next_due_at: datetime | None = None,
        capacity_model_ref: str | None = None,
        capacity_account_ref: str | None = None,
    ) -> None:
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """
                UPDATE knowledge_workbench_rag_eval_runs
                SET status = $3,
                    current_phase = $4,
                    blocked_reason = $5,
                    failed_reason = $6,
                    updated_at = $7,
                    selected_entries = $8,
                    scheduled_generation_items = $9,
                    waiting_work_items = $10,
                    running_work_items = $11,
                    completed_work_items = $12,
                    failed_work_items = $13,
                    generated_question_sets = $14,
                    capacity_next_due_at = $15,
                    capacity_model_ref = $16,
                    capacity_account_ref = $17,
                    adjudication_total = $18,
                    adjudication_waiting = $19,
                    adjudication_running = $20,
                    adjudication_completed = $21,
                    adjudication_failed = $22,
                    promotion_candidate_count = $23
                WHERE run_id = $1 AND project_id = $2::uuid
                """,
                run_id,
                project_id,
                status.value,
                current_phase.value,
                blocked_reason,
                failed_reason,
                updated_at,
                progress.selected_entries,
                progress.scheduled_generation_items,
                progress.waiting,
                progress.running,
                progress.completed,
                progress.failed,
                progress.generated_question_sets,
                capacity_next_due_at,
                capacity_model_ref,
                capacity_account_ref,
                progress.adjudication_total,
                progress.adjudication_waiting,
                progress.adjudication_running,
                progress.adjudication_completed,
                progress.adjudication_failed,
                progress.promotion_candidate_count,
            )

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
                await _insert_rag_eval_question(connection, question)
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

    async def save_question_roles(self, *, roles):
        async with _connection(self._connection_or_pool) as connection:
            for question_id, role in roles.items():
                await connection.execute(
                    """UPDATE knowledge_workbench_rag_eval_questions
                    SET evaluation_role = $2,
                        promotion_eligible = CASE WHEN $2 = 'holdout' THEN FALSE ELSE promotion_eligible END
                    WHERE question_id = $1""",
                    question_id,
                    role.value,
                )

    async def save_retrieval_outcomes(
        self,
        *,
        outcomes: tuple[WorkbenchRagEvalRetrievalOutcome, ...],
    ) -> tuple[WorkbenchRagEvalRetrievalOutcome, ...]:
        async with _connection(self._connection_or_pool) as connection:
            for outcome in outcomes:
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_retrieval_outcomes (
                        outcome_id,
                        run_id,
                        question_id,
                        project_id,
                        evaluation_stage,
                        expected_runtime_entry_id,
                        expected_fact_id,
                        expected_rank,
                        expected_score,
                        best_competitor_runtime_entry_id,
                        best_competitor_fact_id,
                        best_competitor_score,
                        score_margin,
                        classification,
                        created_at
                    )
                    VALUES (
                        $1,
                        $2,
                        $3,
                        $4::uuid,
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
                        $15
                    )
                    ON CONFLICT (
                        run_id,
                        question_id,
                        evaluation_stage
                    )
                    DO UPDATE SET
                        outcome_id = EXCLUDED.outcome_id,
                        project_id = EXCLUDED.project_id,
                        expected_runtime_entry_id = (
                            EXCLUDED.expected_runtime_entry_id
                        ),
                        expected_fact_id = EXCLUDED.expected_fact_id,
                        expected_rank = EXCLUDED.expected_rank,
                        expected_score = EXCLUDED.expected_score,
                        best_competitor_runtime_entry_id = (
                            EXCLUDED.best_competitor_runtime_entry_id
                        ),
                        best_competitor_fact_id = (
                            EXCLUDED.best_competitor_fact_id
                        ),
                        best_competitor_score = (
                            EXCLUDED.best_competitor_score
                        ),
                        score_margin = EXCLUDED.score_margin,
                        classification = EXCLUDED.classification,
                        created_at = EXCLUDED.created_at
                    """,
                    outcome.outcome_id,
                    outcome.run_id,
                    outcome.question_id,
                    outcome.project_id,
                    outcome.evaluation_stage,
                    outcome.expected_runtime_entry_id,
                    outcome.expected_fact_id,
                    outcome.expected_rank,
                    outcome.expected_score,
                    outcome.best_competitor_runtime_entry_id,
                    outcome.best_competitor_fact_id,
                    outcome.best_competitor_score,
                    outcome.score_margin,
                    outcome.classification.value,
                    outcome.created_at,
                )

        return outcomes

    async def mark_questions_evaluated(
        self,
        *,
        run_id: str,
        question_ids: tuple[str, ...],
        evaluated_at: datetime,
    ) -> None:
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """UPDATE knowledge_workbench_rag_eval_questions
                SET status = 'evaluated',
                    evaluated_at = $3
                WHERE run_id = $1 AND question_id = ANY($2::text[])""",
                run_id,
                list(question_ids),
                evaluated_at,
            )

    async def complete_initial_retrieval_evaluation(
        self,
        *,
        run_id: str,
        project_id: str,
        total_questions: int,
        classification_counts: Mapping[str, int],
        updated_at: datetime,
    ) -> None:
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """UPDATE knowledge_workbench_rag_eval_runs
                SET status = 'running',
                    current_phase = 'adjudication_scheduling',
                    retrieval_total_questions = $3,
                    retrieval_evaluated_questions = $3,
                    retrieval_pass_strong = $4,
                    retrieval_pass_weak = $5,
                    retrieval_confusions = $6,
                    retrieval_misses = $7,
                    retrieval_existing_alias_failures = $8,
                    updated_at = $9
                WHERE run_id = $1 AND project_id = $2::uuid""",
                run_id,
                project_id,
                total_questions,
                classification_counts.get("pass_strong", 0),
                classification_counts.get("pass_weak", 0),
                classification_counts.get("confusion", 0),
                classification_counts.get("miss", 0),
                classification_counts.get("existing_alias_retrieval_failure", 0),
                updated_at,
            )

    async def list_adjudication_planning_inputs(
        self,
        *,
        run_id: str,
        project_id: str,
    ) -> tuple[WorkbenchRagEvalAdjudicationPlanningInput, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                SELECT
                    question.run_id,
                    question.project_id::text AS project_id,
                    question.question_id,
                    question.question,
                    question.evaluation_role,
                    question.promotion_eligible,
                    question.ambiguity_risk,
                    outcome.outcome_id,
                    outcome.classification,
                    outcome.expected_runtime_entry_id,
                    outcome.expected_fact_id,
                    outcome.expected_rank,
                    outcome.expected_score,
                    outcome.best_competitor_runtime_entry_id,
                    outcome.best_competitor_fact_id,
                    outcome.best_competitor_score,
                    outcome.score_margin,
                    target.claim AS target_claim,
                    target.possible_questions AS target_possible_questions,
                    target.exclusion_scope AS target_exclusion_scope,
                    target.evidence_block AS target_evidence_block,
                    result.rank AS retrieved_rank,
                    result.matched_runtime_entry_id AS retrieved_runtime_entry_id,
                    result.matched_fact_id AS retrieved_fact_id,
                    result.score AS retrieved_score,
                    retrieved.claim AS retrieved_claim
                FROM knowledge_workbench_rag_eval_questions AS question
                JOIN knowledge_workbench_rag_eval_retrieval_outcomes AS outcome
                  ON outcome.run_id = question.run_id
                 AND outcome.question_id = question.question_id
                 AND outcome.project_id = question.project_id
                 AND outcome.evaluation_stage = 'initial'
                JOIN knowledge_workbench_runtime_retrieval_entries AS target
                  ON target.project_id = question.project_id
                 AND target.runtime_entry_id = outcome.expected_runtime_entry_id
                LEFT JOIN knowledge_workbench_rag_eval_retrieval_results AS result
                  ON result.run_id = question.run_id
                 AND result.question_id = question.question_id
                 AND result.project_id = question.project_id
                LEFT JOIN knowledge_workbench_runtime_retrieval_entries AS retrieved
                  ON retrieved.project_id = question.project_id
                 AND retrieved.runtime_entry_id = result.matched_runtime_entry_id
                WHERE question.run_id = $1
                  AND question.project_id = $2::uuid
                ORDER BY question.created_at, question.question_id, result.rank NULLS LAST
                """,
                run_id,
                project_id,
            )
        return _adjudication_planning_inputs_from_rows(rows)

    async def save_question_adjudication(
        self,
        *,
        adjudication: WorkbenchRagEvalAdjudication,
    ) -> WorkbenchRagEvalAdjudication:
        async with _connection(self._connection_or_pool) as connection:
            existing = await connection.fetchrow(
                """
                SELECT
                    adjudication_id, run_id, project_id::text AS project_id,
                    question_id, outcome_id, expected_runtime_entry_id,
                    expected_fact_id, verdict, promotion_recommended, reason,
                    contract_version, model_ref, account_ref, slot_index,
                    attempt_id, created_at, updated_at
                FROM knowledge_workbench_rag_eval_question_adjudications
                WHERE run_id = $1 AND question_id = $2 AND outcome_id = $3
                """,
                adjudication.run_id,
                adjudication.question_id,
                adjudication.outcome_id,
            )
            if existing is not None:
                hydrated = _adjudication_from_row(existing)
                if hydrated == adjudication:
                    return hydrated
                raise ValueError("adjudication immutable identity/context conflict")
            await connection.execute(
                """
                INSERT INTO knowledge_workbench_rag_eval_question_adjudications (
                    adjudication_id, run_id, project_id, question_id,
                    outcome_id, expected_runtime_entry_id, expected_fact_id,
                    verdict, promotion_recommended, reason, contract_version,
                    model_ref, account_ref, slot_index, attempt_id,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, $3::uuid, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17
                )
                """,
                adjudication.adjudication_id,
                adjudication.run_id,
                adjudication.project_id,
                adjudication.question_id,
                adjudication.outcome_id,
                adjudication.expected_runtime_entry_id,
                adjudication.expected_fact_id,
                adjudication.verdict.value,
                adjudication.promotion_recommended,
                adjudication.reason,
                adjudication.contract_version,
                adjudication.model_ref,
                adjudication.account_ref,
                adjudication.slot_index,
                adjudication.attempt_id,
                adjudication.created_at,
                adjudication.updated_at,
            )
        return adjudication

    async def has_adjudications_for_all_eligible_questions(
        self,
        *,
        run_id: str,
        project_id: str,
        pass_weak_enabled: bool,
    ) -> bool:
        inputs = await self.list_adjudication_planning_inputs(
            run_id=run_id,
            project_id=project_id,
        )
        policy = WorkbenchRagEvalAdjudicationEligibilityPolicy(
            pass_weak_enabled=pass_weak_enabled
        )
        eligible = tuple(
            item
            for item in inputs
            if policy.is_eligible(
                evaluation_role=item.evaluation_role,
                promotion_eligible=item.promotion_eligible,
                ambiguity_risk=item.ambiguity_risk,
                classification=item.classification,
            )
        )
        if not eligible:
            return True
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                SELECT question_id, outcome_id
                FROM knowledge_workbench_rag_eval_question_adjudications
                WHERE run_id = $1 AND project_id = $2::uuid
                """,
                run_id,
                project_id,
            )
        persisted = {
            (_text_from_row(row, "question_id"), _text_from_row(row, "outcome_id"))
            for row in rows
        }
        return all(
            (item.question_id, item.outcome_id) in persisted for item in eligible
        )

    async def create_promotion_candidates_from_adjudications(
        self,
        *,
        run_id: str,
        project_id: str,
        created_at: datetime,
        pass_weak_enabled: bool,
    ) -> tuple[WorkbenchRagEvalPromotedQuestion, ...]:
        policy = WorkbenchRagEvalAdjudicationEligibilityPolicy(
            pass_weak_enabled=pass_weak_enabled
        )
        inputs = await self.list_adjudication_planning_inputs(
            run_id=run_id,
            project_id=project_id,
        )
        eligible_by_key = {
            (item.question_id, item.outcome_id): item
            for item in inputs
            if policy.is_eligible(
                evaluation_role=item.evaluation_role,
                promotion_eligible=item.promotion_eligible,
                ambiguity_risk=item.ambiguity_risk,
                classification=item.classification,
            )
        }
        if not eligible_by_key:
            await self._persist_promotion_review_state(
                run_id=run_id,
                project_id=project_id,
                candidate_count=0,
                updated_at=created_at,
            )
            return ()
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                SELECT
                    adjudication_id, run_id, project_id::text AS project_id,
                    question_id, outcome_id, expected_runtime_entry_id,
                    expected_fact_id, verdict, promotion_recommended, reason,
                    contract_version, model_ref, account_ref, slot_index,
                    attempt_id, created_at, updated_at
                FROM knowledge_workbench_rag_eval_question_adjudications
                WHERE run_id = $1 AND project_id = $2::uuid
                  AND verdict = 'valid_target_query'
                  AND promotion_recommended = TRUE
                """,
                run_id,
                project_id,
            )
            promotions: list[WorkbenchRagEvalPromotedQuestion] = []
            for row in rows:
                adjudication = _adjudication_from_row(row)
                item = eligible_by_key.get(
                    (adjudication.question_id, adjudication.outcome_id)
                )
                if item is None:
                    continue
                promotion = WorkbenchRagEvalPromotedQuestion(
                    promotion_id=_promotion_id(adjudication.adjudication_id),
                    run_id=run_id,
                    question_id=item.question_id,
                    project_id=project_id,
                    target_runtime_entry_id=item.expected_runtime_entry_id,
                    target_fact_id=item.expected_fact_id,
                    question=item.question,
                    status=WorkbenchRagEvalPromotionStatus.CANDIDATE,
                    created_at=created_at,
                    applied_at=None,
                    outcome_id=item.outcome_id,
                    adjudication_id=adjudication.adjudication_id,
                    reason=adjudication.reason,
                    expected_rank=item.expected_rank,
                    expected_score=item.expected_score,
                    competitor_runtime_entry_id=(item.best_competitor_runtime_entry_id),
                    competitor_fact_id=item.best_competitor_fact_id,
                    competitor_score=item.best_competitor_score,
                    score_margin=item.score_margin,
                )
                promotions.append(promotion)
                await _insert_promotion_candidate(connection, promotion)
            await self._persist_promotion_review_state(
                run_id=run_id,
                project_id=project_id,
                candidate_count=len(promotions),
                updated_at=created_at,
            )
        return tuple(promotions)

    async def _persist_promotion_review_state(
        self,
        *,
        run_id: str,
        project_id: str,
        candidate_count: int,
        updated_at: datetime,
    ) -> None:
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """
                UPDATE knowledge_workbench_rag_eval_runs
                SET status = 'promotion_review',
                    current_phase = 'promotion_review',
                    promotion_candidate_count = $3,
                    updated_at = $4
                WHERE run_id = $1 AND project_id = $2::uuid
                """,
                run_id,
                project_id,
                candidate_count,
                updated_at,
            )

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
                        status, created_at, applied_at, outcome_id,
                        adjudication_id, reason, expected_rank, expected_score,
                        competitor_runtime_entry_id, competitor_fact_id,
                        competitor_score, score_margin
                    )
                    VALUES (
                        $1, $2, $3, $4::uuid, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18, $19
                    )
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
                    promotion.outcome_id,
                    promotion.adjudication_id,
                    promotion.reason,
                    promotion.expected_rank,
                    promotion.expected_score,
                    promotion.competitor_runtime_entry_id,
                    promotion.competitor_fact_id,
                    promotion.competitor_score,
                    promotion.score_margin,
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
                    run.run_id,
                    run.project_id::text AS project_id,
                    run.publication_id,
                    run.source_document_ref,
                    run.status,
                    run.current_phase,
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
                    run.blocked_reason,
                    run.failed_reason,
                    run.updated_at,
                    run.selected_entries,
                    run.scheduled_generation_items,
                    run.waiting_work_items,
                    run.running_work_items,
                    run.completed_work_items,
                    run.failed_work_items,
                    run.generated_question_sets,
                    run.capacity_next_due_at,
                    run.capacity_model_ref,
                    run.capacity_account_ref,
                    run.retrieval_total_questions,
                    run.retrieval_evaluated_questions,
                    run.retrieval_pass_strong,
                    run.retrieval_pass_weak,
                    run.retrieval_confusions,
                    run.retrieval_misses,
                    run.retrieval_existing_alias_failures,
                    run.adjudication_total,
                    run.adjudication_waiting,
                    run.adjudication_running,
                    run.adjudication_completed,
                    run.adjudication_failed,
                    run.promotion_candidate_count AS persisted_promotion_candidate_count,
                    (
                        SELECT count(*)
                        FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
                        WHERE promotion.run_id = run.run_id
                          AND promotion.status = 'candidate'
                    ) AS computed_promotion_candidate_count
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
                    run.run_id,
                    run.project_id::text AS project_id,
                    run.publication_id,
                    run.source_document_ref,
                    run.status,
                    run.current_phase,
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
                    run.blocked_reason,
                    run.failed_reason,
                    run.updated_at,
                    run.selected_entries,
                    run.scheduled_generation_items,
                    run.waiting_work_items,
                    run.running_work_items,
                    run.completed_work_items,
                    run.failed_work_items,
                    run.generated_question_sets,
                    run.capacity_next_due_at,
                    run.capacity_model_ref,
                    run.capacity_account_ref,
                    run.retrieval_total_questions,
                    run.retrieval_evaluated_questions,
                    run.retrieval_pass_strong,
                    run.retrieval_pass_weak,
                    run.retrieval_confusions,
                    run.retrieval_misses,
                    run.retrieval_existing_alias_failures,
                    run.adjudication_total,
                    run.adjudication_waiting,
                    run.adjudication_running,
                    run.adjudication_completed,
                    run.adjudication_failed,
                    run.promotion_candidate_count AS persisted_promotion_candidate_count,
                    (
                        SELECT count(*)
                        FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
                        WHERE promotion.run_id = run.run_id
                          AND promotion.status = 'candidate'
                    ) AS computed_promotion_candidate_count
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

    async def list_promotion_application_targets_for_ids(
        self,
        *,
        project_id: str,
        promotion_ids: Sequence[str],
    ) -> tuple[WorkbenchRagEvalPromotionApplicationTarget, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_BY_IDS_SQL,
                project_id,
                list(promotion_ids),
            )
        return tuple(_promotion_application_target_from_row(row) for row in rows)

    async def list_promotion_application_targets_for_run(
        self,
        *,
        project_id: str,
        run_id: str,
    ) -> tuple[WorkbenchRagEvalPromotionApplicationTarget, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_RUN_SQL,
                project_id,
                run_id,
            )
        return tuple(_promotion_application_target_from_row(row) for row in rows)

    async def apply_promotion_candidates_for_target(
        self,
        *,
        project_id: str,
        promotion_ids: Sequence[str],
        target_runtime_entry_id: str,
        embedding_model_id: str,
        dimensions: int,
        embedding: Sequence[float],
        embedding_text: str,
        embedding_text_hash: str,
        applied_at: datetime,
    ) -> tuple[WorkbenchRagEvalPromotionApplyResult, ...]:
        requested_ids = tuple(promotion_ids)
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_UPDATE_SQL,
                    project_id,
                    list(requested_ids),
                    target_runtime_entry_id,
                )
                if len(rows) != len(requested_ids):
                    raise LookupError("Promotion candidates not found for target")

                targets = tuple(
                    _promotion_application_target_from_row(row) for row in rows
                )
                for target in targets:
                    if target.target_runtime_entry_id != target_runtime_entry_id:
                        raise RuntimeError("Promotion target runtime entry mismatch")
                    if target.status not in (
                        WorkbenchRagEvalPromotionStatus.CANDIDATE,
                        WorkbenchRagEvalPromotionStatus.ACCEPTED,
                    ):
                        raise RuntimeError(
                            "Promotion candidate status cannot be applied: "
                            f"{target.status.value}"
                        )

                base = targets[0]
                runtime_questions = _append_texts_once(
                    base.runtime_possible_questions,
                    tuple(target.question for target in targets),
                )

                await connection.execute(
                    """
                    UPDATE knowledge_workbench_runtime_retrieval_entries
                    SET possible_questions = $3::jsonb,
                        embedding_text = $4
                    WHERE project_id = $1::uuid
                      AND runtime_entry_id = $2
                      AND visibility = 'published'
                      AND status = 'active'
                    """,
                    project_id,
                    base.target_runtime_entry_id,
                    _json_text_list(runtime_questions),
                    embedding_text,
                )
                await connection.execute(
                    """
                    DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
                    WHERE runtime_entry_id = $1
                      AND embedding_model_id = $2
                    """,
                    base.target_runtime_entry_id,
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
                    base.target_runtime_entry_id,
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
                        applied_at = $4
                    WHERE project_id = $1::uuid
                      AND promotion_id = ANY($2::text[])
                      AND target_runtime_entry_id = $3
                    """,
                    project_id,
                    list(requested_ids),
                    target_runtime_entry_id,
                    applied_at,
                )

        return tuple(
            WorkbenchRagEvalPromotionApplyResult(
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
            for target in targets
        )

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

                await connection.execute(
                    """
                    UPDATE knowledge_workbench_runtime_retrieval_entries
                    SET possible_questions = $3::jsonb,
                        embedding_text = $4
                    WHERE project_id = $1::uuid
                      AND runtime_entry_id = $2
                      AND visibility = 'published'
                      AND status = 'active'
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
    contract_version: str | None
    promotion_eligible: bool
    ambiguity_risk: WorkbenchRagEvalQuestionAmbiguityRisk | None
    generation_rationale: str | None
    generation_account_ref: str | None
    generation_slot_index: int | None
    evaluation_role: WorkbenchRagEvalQuestionRole
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
            contract_version=self.contract_version,
            promotion_eligible=self.promotion_eligible,
            ambiguity_risk=self.ambiguity_risk,
            generation_rationale=self.generation_rationale,
            generation_account_ref=self.generation_account_ref,
            generation_slot_index=self.generation_slot_index,
            evaluation_role=self.evaluation_role,
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
                contract_version=_optional_text_from_row(
                    row,
                    "contract_version",
                ),
                promotion_eligible=_bool_from_row(
                    row,
                    "promotion_eligible",
                ),
                ambiguity_risk=(
                    WorkbenchRagEvalQuestionAmbiguityRisk(ambiguity_risk)
                    if (
                        ambiguity_risk := _optional_text_from_row(
                            row,
                            "ambiguity_risk",
                        )
                    )
                    is not None
                    else None
                ),
                generation_rationale=_optional_text_from_row(
                    row,
                    "generation_rationale",
                ),
                generation_account_ref=_optional_text_from_row(
                    row, "generation_account_ref"
                ),
                generation_slot_index=_optional_int_from_row(
                    row, "generation_slot_index"
                ),
                evaluation_role=WorkbenchRagEvalQuestionRole(
                    _text_from_row(row, "evaluation_role")
                ),
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
        current_phase=WorkbenchRagEvalCurrentPhase(
            _text_from_row(row, "current_phase")
        ),
        total_entries=_int_from_row(row, "total_entries"),
        total_questions=_int_from_row(row, "total_questions"),
        completed_questions=_int_from_row(row, "completed_questions"),
        top1_hits=_int_from_row(row, "top1_hits"),
        top3_hits=_int_from_row(row, "top3_hits"),
        top5_hits=_int_from_row(row, "top5_hits"),
        misses=_int_from_row(row, "misses"),
        promotion_candidate_count=_int_from_row_default_zero(
            row, "persisted_promotion_candidate_count"
        ),
        created_at=_datetime_from_row(row, "created_at"),
        completed_at=_optional_datetime_from_row(row, "completed_at"),
        error_message=_optional_text_from_row(row, "error_message"),
        blocked_reason=_optional_text_from_row(row, "blocked_reason"),
        failed_reason=_optional_text_from_row(row, "failed_reason"),
        updated_at=_optional_datetime_from_row(row, "updated_at"),
        progress=WorkbenchRagEvalRunProgress(
            selected_entries=_int_from_row(row, "selected_entries"),
            scheduled_generation_items=_int_from_row(row, "scheduled_generation_items"),
            waiting=_int_from_row(row, "waiting_work_items"),
            running=_int_from_row(row, "running_work_items"),
            completed=_int_from_row(row, "completed_work_items"),
            failed=_int_from_row(row, "failed_work_items"),
            generated_question_sets=_int_from_row(row, "generated_question_sets"),
            adjudication_total=_int_from_row_default_zero(row, "adjudication_total"),
            adjudication_waiting=_int_from_row_default_zero(
                row, "adjudication_waiting"
            ),
            adjudication_running=_int_from_row_default_zero(
                row, "adjudication_running"
            ),
            adjudication_completed=_int_from_row_default_zero(
                row, "adjudication_completed"
            ),
            adjudication_failed=_int_from_row_default_zero(row, "adjudication_failed"),
            promotion_candidate_count=_int_from_row_default_zero(
                row, "persisted_promotion_candidate_count"
            ),
        ),
        capacity_next_due_at=_optional_datetime_from_row(row, "capacity_next_due_at"),
        capacity_model_ref=_optional_text_from_row(row, "capacity_model_ref"),
        capacity_account_ref=_optional_text_from_row(row, "capacity_account_ref"),
        retrieval_total_questions=_int_from_row_default_zero(
            row, "retrieval_total_questions"
        ),
        retrieval_evaluated_questions=_int_from_row_default_zero(
            row, "retrieval_evaluated_questions"
        ),
        retrieval_pass_strong=_int_from_row_default_zero(row, "retrieval_pass_strong"),
        retrieval_pass_weak=_int_from_row_default_zero(row, "retrieval_pass_weak"),
        retrieval_confusions=_int_from_row_default_zero(row, "retrieval_confusions"),
        retrieval_misses=_int_from_row_default_zero(row, "retrieval_misses"),
        retrieval_existing_alias_failures=_int_from_row_default_zero(
            row, "retrieval_existing_alias_failures"
        ),
    )


def _adjudication_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalAdjudication:
    return WorkbenchRagEvalAdjudication(
        adjudication_id=_text_from_row(row, "adjudication_id"),
        run_id=_text_from_row(row, "run_id"),
        project_id=_text_from_row(row, "project_id"),
        question_id=_text_from_row(row, "question_id"),
        outcome_id=_text_from_row(row, "outcome_id"),
        expected_runtime_entry_id=_text_from_row(row, "expected_runtime_entry_id"),
        expected_fact_id=_text_from_row(row, "expected_fact_id"),
        verdict=WorkbenchRagEvalAdjudicationVerdict(_text_from_row(row, "verdict")),
        promotion_recommended=_bool_from_row(row, "promotion_recommended"),
        reason=_text_from_row(row, "reason"),
        contract_version=_text_from_row(row, "contract_version"),
        model_ref=_text_from_row(row, "model_ref"),
        account_ref=_text_from_row(row, "account_ref"),
        slot_index=_int_from_row(row, "slot_index"),
        attempt_id=_text_from_row(row, "attempt_id"),
        created_at=_datetime_from_row(row, "created_at"),
        updated_at=_datetime_from_row(row, "updated_at"),
    )


def _adjudication_planning_inputs_from_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[WorkbenchRagEvalAdjudicationPlanningInput, ...]:
    drafts: dict[tuple[str, str], dict[str, object]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (_text_from_row(row, "question_id"), _text_from_row(row, "outcome_id"))
        if key not in drafts:
            drafts[key] = {
                "row": row,
                "retrieved": [],
            }
            order.append(key)
        if row.get("retrieved_runtime_entry_id") is not None:
            retrieved = drafts[key]["retrieved"]
            if not isinstance(retrieved, list):
                raise TypeError("retrieved draft must be list")
            retrieved.append(
                WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot(
                    rank=_int_from_row(row, "retrieved_rank"),
                    runtime_entry_id=_text_from_row(row, "retrieved_runtime_entry_id"),
                    fact_id=_text_from_row(row, "retrieved_fact_id"),
                    claim=_text_from_row(row, "retrieved_claim"),
                    score=_float_from_row(row, "retrieved_score"),
                )
            )
    result: list[WorkbenchRagEvalAdjudicationPlanningInput] = []
    for key in order:
        draft = drafts[key]
        row = cast(Mapping[str, object], draft["row"])
        retrieved = cast(
            list[WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot],
            draft["retrieved"],
        )
        if not isinstance(row, Mapping) or not isinstance(retrieved, list):
            raise TypeError("invalid adjudication planning draft")
        ambiguity_risk = _optional_text_from_row(row, "ambiguity_risk")
        result.append(
            WorkbenchRagEvalAdjudicationPlanningInput(
                run_id=_text_from_row(row, "run_id"),
                project_id=_text_from_row(row, "project_id"),
                question_id=_text_from_row(row, "question_id"),
                question=_text_from_row(row, "question"),
                evaluation_role=WorkbenchRagEvalQuestionRole(
                    _text_from_row(row, "evaluation_role")
                ),
                promotion_eligible=_bool_from_row(row, "promotion_eligible"),
                ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk(ambiguity_risk)
                if ambiguity_risk is not None
                else None,
                outcome_id=_text_from_row(row, "outcome_id"),
                classification=WorkbenchRagEvalRetrievalClassification(
                    _text_from_row(row, "classification")
                ),
                expected_runtime_entry_id=_text_from_row(
                    row, "expected_runtime_entry_id"
                ),
                expected_fact_id=_text_from_row(row, "expected_fact_id"),
                expected_rank=_optional_int_from_row(row, "expected_rank"),
                expected_score=_optional_float_from_row(row, "expected_score"),
                best_competitor_runtime_entry_id=_optional_text_from_row(
                    row, "best_competitor_runtime_entry_id"
                ),
                best_competitor_fact_id=_optional_text_from_row(
                    row, "best_competitor_fact_id"
                ),
                best_competitor_score=_optional_float_from_row(
                    row, "best_competitor_score"
                ),
                score_margin=_optional_float_from_row(row, "score_margin"),
                target_claim=_text_from_row(row, "target_claim"),
                target_possible_questions=_text_tuple(
                    row.get("target_possible_questions")
                ),
                target_exclusion_scope=_optional_text_from_row(
                    row, "target_exclusion_scope"
                ),
                target_evidence_block=_optional_text_from_row(
                    row, "target_evidence_block"
                )
                or "",
                retrieved=tuple(retrieved),
            )
        )
    return tuple(result)


def _optional_float_from_row(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric or None")
    return float(value)


async def _insert_promotion_candidate(
    connection: WorkbenchRagEvalConnectionLike,
    promotion: WorkbenchRagEvalPromotedQuestion,
) -> None:
    await connection.execute(
        """
        INSERT INTO knowledge_workbench_rag_eval_promoted_questions (
            promotion_id, run_id, question_id, project_id,
            target_runtime_entry_id, target_fact_id, question,
            status, created_at, applied_at, outcome_id, adjudication_id,
            reason, expected_rank, expected_score,
            competitor_runtime_entry_id, competitor_fact_id,
            competitor_score, score_margin
        )
        VALUES (
            $1, $2, $3, $4::uuid, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19
        )
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
        promotion.outcome_id,
        promotion.adjudication_id,
        promotion.reason,
        promotion.expected_rank,
        promotion.expected_score,
        promotion.competitor_runtime_entry_id,
        promotion.competitor_fact_id,
        promotion.competitor_score,
        promotion.score_margin,
    )


def _promotion_id(adjudication_id: str) -> str:
    return "rag-eval-promotion:" + sha256(adjudication_id.encode("utf-8")).hexdigest()


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


def _append_texts_once(
    values: tuple[str, ...],
    additions: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in (*values, *additions):
        stripped = item.strip()
        if not stripped:
            continue
        normalized = " ".join(stripped.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(stripped)
    return tuple(result)


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
    return hydrate_jsonb_text_array_payload(
        value,
        field_name="knowledge_workbench_rag_eval.text_array",
    )


def _int_from_row(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _int_from_row_default_zero(row: Mapping[str, object], key: str) -> int:
    value = row.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _optional_int_from_row(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int or None")
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


def _baseline_questions_from_schedule_rows(
    *,
    rows: Sequence[Mapping[str, object]],
    run_id: str,
    project_id: str,
    created_at: datetime,
) -> tuple[WorkbenchRagEvalQuestion, ...]:
    questions_by_id: dict[str, WorkbenchRagEvalQuestion] = {}
    for row in rows:
        row_run_id = _text_from_row(row, "run_id")
        row_project_id = _text_from_row(row, "project_id")
        if row_run_id != run_id or row_project_id != project_id:
            raise ValueError("baseline schedule row does not match requested run")
        runtime_entry_id = _text_from_row(row, "runtime_entry_id")
        question = _text_from_row(row, "question")
        normalized_question = normalize_workbench_rag_eval_question(question)
        if not normalized_question:
            raise ValueError("baseline question normalizes to empty text")
        question_id = _baseline_question_id(
            run_id=run_id,
            runtime_entry_id=runtime_entry_id,
            normalized_question=normalized_question,
        )
        questions_by_id.setdefault(
            question_id,
            WorkbenchRagEvalQuestion(
                question_id=question_id,
                run_id=run_id,
                project_id=project_id,
                expected_runtime_entry_id=runtime_entry_id,
                expected_fact_id=_text_from_row(row, "expected_fact_id"),
                question=question.strip(),
                question_kind=WorkbenchRagEvalQuestionKind.EXISTING_POSSIBLE_QUESTION,
                source=WorkbenchRagEvalQuestionSource.PUBLISHED_POSSIBLE_QUESTION,
                generation_model=None,
                prompt_version=None,
                contract_version=None,
                promotion_eligible=False,
                ambiguity_risk=None,
                generation_rationale=None,
                generation_account_ref=None,
                generation_slot_index=None,
                status=WorkbenchRagEvalQuestionStatus.CREATED,
                created_at=created_at,
                evaluation_role=WorkbenchRagEvalQuestionRole.BASELINE,
            ),
        )
    return tuple(questions_by_id.values())


def _baseline_question_id(
    *,
    run_id: str,
    runtime_entry_id: str,
    normalized_question: str,
) -> str:
    return (
        "rag-eval-baseline:"
        + sha256(
            "\x1f".join(
                (
                    run_id,
                    runtime_entry_id,
                    WorkbenchRagEvalQuestionSource.PUBLISHED_POSSIBLE_QUESTION.value,
                    normalized_question,
                )
            ).encode("utf-8")
        ).hexdigest()
    )


async def _insert_rag_eval_question(
    connection: WorkbenchRagEvalConnectionLike,
    question: WorkbenchRagEvalQuestion,
) -> bool:
    result = await connection.execute(
        """
        INSERT INTO knowledge_workbench_rag_eval_questions (
            question_id, run_id, project_id,
            expected_runtime_entry_id, expected_fact_id, question,
            question_kind, source, generation_model, prompt_version,
            contract_version, promotion_eligible, ambiguity_risk,
            generation_rationale, generation_account_ref,
            generation_slot_index, status, created_at, evaluation_role
        )
        VALUES (
            $1, $2, $3::uuid, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, $19
        )
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
        question.contract_version,
        question.promotion_eligible,
        question.ambiguity_risk.value if question.ambiguity_risk is not None else None,
        question.generation_rationale,
        question.generation_account_ref,
        question.generation_slot_index,
        question.status.value,
        question.created_at,
        question.evaluation_role.value,
    )
    if isinstance(result, str) and result.startswith("INSERT 0 "):
        return result.endswith(" 1")
    return False
