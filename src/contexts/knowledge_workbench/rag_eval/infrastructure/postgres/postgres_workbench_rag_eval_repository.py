from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Protocol, cast

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
    WorkbenchRagEvalPromotionNotFoundError,
)
from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_review_errors import (
    WorkbenchRagEvalPromotionCandidateConflictError,
    WorkbenchRagEvalPromotionCandidateNotFoundError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalAdjudication,
    WorkbenchRagEvalAdjudicationVerdict,
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionCandidateDetails,
    WorkbenchRagEvalPromotionStatus,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRetrievalOutcome,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRetrievalResultDetails,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalEmbeddingRevisionAvailableActions,
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionReadModel,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationClaim,
    WorkbenchRagEvalPromotionApplicationClaimDecision,
    WorkbenchRagEvalPromotionApplicationClaimDecisionCode,
    WorkbenchRagEvalPromotionApplicationClaimStatus,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_promotion_application_key,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_verification import (
    WORKBENCH_RAG_EVAL_VERIFICATION_POLICY_VERSION,
    WorkbenchRagEvalVerificationDecision,
    WorkbenchRagEvalVerificationDatasetRole,
    WorkbenchRagEvalVerificationFailureReason,
    WorkbenchRagEvalVerificationMetrics,
    WorkbenchRagEvalVerificationOutcomePair,
    WorkbenchRagEvalVerificationPolicyDecision,
    WorkbenchRagEvalVerificationQuery,
    WorkbenchRagEvalVerificationReadModel,
    WorkbenchRagEvalVerificationSearchObservation,
    WorkbenchRagEvalVerificationStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_retrieval_outcome_policy import (
    WorkbenchRagEvalRetrievalOutcomePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowEventType,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_text_array_payload,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_review_transition_policy import (
    WorkbenchRagEvalPromotionReviewTransitionConflictError,
    WorkbenchRagEvalPromotionReviewTransitionPolicy,
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
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


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


WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_COLUMNS_SQL = """
    promotion_id,
    run_id,
    question_id,
    project_id::text AS project_id,
    outcome_id,
    adjudication_id,
    target_runtime_entry_id,
    target_fact_id,
    question,
    status,
    reason,
    expected_rank,
    expected_score,
    competitor_runtime_entry_id,
    competitor_fact_id,
    competitor_score,
    score_margin,
    created_at,
    reviewed_at,
    review_reason,
    applied_at
"""


WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL = (
    "SELECT"
    + WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_COLUMNS_SQL
    + """
FROM knowledge_workbench_rag_eval_promoted_questions
WHERE project_id = $1::uuid
  AND run_id = $2
ORDER BY created_at, promotion_id
"""
)


WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_BY_ID_SQL = (
    "SELECT"
    + WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_COLUMNS_SQL
    + """
FROM knowledge_workbench_rag_eval_promoted_questions
WHERE project_id = $1::uuid
  AND promotion_id = $2
"""
)


WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_FOR_REVIEW_SQL = (
    "SELECT"
    + WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_COLUMNS_SQL
    + """
FROM knowledge_workbench_rag_eval_promoted_questions
WHERE promotion_id = $1
  AND run_id = $2
  AND project_id = $3::uuid
FOR UPDATE
"""
)

_VERIFICATION_READ_SQL = """
SELECT
    verification.verification_id,
    verification.revision_id,
    verification.project_id::text AS project_id,
    verification.source_rag_eval_run_id,
    verification.runtime_entry_id,
    verification.status,
    verification.policy_version,
    verification.decision,
    verification.failure_reasons,
    verification.metrics,
    verification.created_at,
    verification.completed_at,
    verification.failed_at,
    verification.error_message,
    COUNT(DISTINCT query.verification_query_id)::int AS query_count,
    COUNT(DISTINCT outcome.verification_outcome_id)::int AS outcome_count
FROM knowledge_workbench_rag_eval_verifications AS verification
LEFT JOIN knowledge_workbench_rag_eval_verification_queries AS query
  ON query.verification_id = verification.verification_id
LEFT JOIN knowledge_workbench_rag_eval_verification_outcomes AS outcome
  ON outcome.verification_id = verification.verification_id
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
    entry.embedding_text AS existing_embedding_text
FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
JOIN knowledge_workbench_runtime_retrieval_entries AS entry
  ON entry.runtime_entry_id = promotion.target_runtime_entry_id
 AND entry.project_id = promotion.project_id
WHERE promotion.project_id = $1::uuid
  AND promotion.promotion_id = $2
"""


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_BY_IDS_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL.replace(
        "promotion.promotion_id = $2",
        "promotion.promotion_id = ANY($2::text[])",
    )
)


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_RUN_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL.replace(
        "promotion.promotion_id = $2",
        ("promotion.run_id = $2 AND promotion.status IN ('approved', 'applied')"),
    )
)


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL = """
SELECT
    promotion.promotion_id,
    promotion.run_id,
    promotion.question_id,
    promotion.project_id::text AS project_id,
    promotion.target_runtime_entry_id,
    promotion.target_fact_id,
    promotion.question,
    promotion.status,
    entry.runtime_entry_id,
    COALESCE(NULLIF(entry.fact_id, ''), entry.runtime_entry_id) AS fact_id,
    entry.status AS runtime_status,
    entry.visibility AS runtime_visibility,
    entry.claim,
    entry.possible_questions,
    applied_aliases.active_promoted_questions,
    entry.exclusion_scope,
    entry.embedding_text,
    emb.embedding_model_id,
    emb.dimensions AS embedding_dimensions,
    emb.embedding::text AS current_embedding,
    active.revision_id AS active_revision_id
FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
JOIN knowledge_workbench_runtime_retrieval_entries AS entry
  ON entry.runtime_entry_id = promotion.target_runtime_entry_id
 AND entry.project_id = promotion.project_id
LEFT JOIN LATERAL (
    SELECT
        current_embedding.embedding_model_id,
        current_embedding.dimensions,
        current_embedding.embedding,
        current_embedding.embedding_text_hash,
        current_embedding.created_at
    FROM knowledge_workbench_runtime_retrieval_entry_embeddings AS current_embedding
    WHERE current_embedding.runtime_entry_id = entry.runtime_entry_id
      AND current_embedding.embedding_model_id = $4
    ORDER BY current_embedding.created_at DESC,
             current_embedding.embedding_text_hash DESC
    LIMIT 1
) AS emb ON TRUE
LEFT JOIN LATERAL (
    SELECT COALESCE(
        jsonb_agg(applied.question ORDER BY applied.promotion_id),
        '[]'::jsonb
    ) AS active_promoted_questions
    FROM knowledge_workbench_rag_eval_promoted_questions AS applied
    WHERE applied.project_id = promotion.project_id
      AND applied.target_runtime_entry_id = promotion.target_runtime_entry_id
      AND applied.status = 'applied'
) AS applied_aliases ON TRUE
LEFT JOIN LATERAL (
    SELECT revision.revision_id
    FROM knowledge_workbench_rag_eval_embedding_revisions AS revision
    WHERE revision.project_id = promotion.project_id
      AND revision.runtime_entry_id = promotion.target_runtime_entry_id
      AND revision.status = 'pending_verification'
    ORDER BY revision.created_at DESC, revision.revision_id
    LIMIT 1
) AS active ON TRUE
WHERE promotion.project_id = $1::uuid
  AND promotion.promotion_id = ANY($2::text[])
  AND promotion.target_runtime_entry_id = $3
ORDER BY promotion.promotion_id
"""


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_FOR_UPDATE_SQL = (
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL
    + " FOR UPDATE OF promotion, entry"
)


WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_COLUMNS_SQL = """
    revision_id,
    project_id::text AS project_id,
    runtime_entry_id,
    source_rag_eval_run_id,
    promotion_ids,
    status,
    previous_promoted_questions,
    new_promoted_questions,
    created_at,
    accepted_at,
    regression_failed_at,
    rolled_back_at,
    EXISTS (
        SELECT 1
        FROM knowledge_workbench_rag_eval_verifications AS action_verification
        WHERE action_verification.revision_id =
            knowledge_workbench_rag_eval_embedding_revisions.revision_id
          AND action_verification.status = 'passed'
          AND action_verification.decision = 'acceptable'
          AND knowledge_workbench_rag_eval_embedding_revisions.status =
              'pending_verification'
    ) AS can_accept,
    (
        knowledge_workbench_rag_eval_embedding_revisions.status = 'regression_failed'
        OR EXISTS (
            SELECT 1
            FROM knowledge_workbench_rag_eval_verifications AS action_verification
            WHERE action_verification.revision_id =
                knowledge_workbench_rag_eval_embedding_revisions.revision_id
              AND action_verification.status = 'regression_failed'
              AND action_verification.decision = 'regression'
        )
    ) AS can_rollback
"""

WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_FULL_COLUMNS_SQL = """
    revision_id,
    project_id::text AS project_id,
    runtime_entry_id,
    source_rag_eval_run_id,
    promotion_ids,
    status,
    previous_embedding_text,
    new_embedding_text,
    previous_embedding::text AS previous_embedding,
    new_embedding::text AS new_embedding,
    previous_promoted_questions,
    new_promoted_questions,
    embedding_model_id,
    embedding_dimensions,
    previous_runtime_hash,
    new_runtime_hash,
    created_at,
    accepted_at,
    regression_failed_at,
    rolled_back_at
"""


WORKBENCH_RAG_EVAL_ACTIVE_EMBEDDING_REVISION_SQL = (
    "SELECT "
    + WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_COLUMNS_SQL
    + """
FROM knowledge_workbench_rag_eval_embedding_revisions
WHERE project_id = $1::uuid
  AND runtime_entry_id = $2
  AND status = 'pending_verification'
"""
)


WORKBENCH_RAG_EVAL_PENDING_REVISION_FOR_PROMOTIONS_SQL = (
    "SELECT "
    + WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_COLUMNS_SQL
    + """
FROM knowledge_workbench_rag_eval_embedding_revisions
WHERE project_id = $1::uuid
  AND runtime_entry_id = $2
  AND source_rag_eval_run_id = $3
  AND promotion_ids = $4::jsonb
  AND status = 'pending_verification'
"""
)


WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL = """
    application_key,
    project_id::text AS project_id,
    runtime_entry_id,
    source_rag_eval_run_id,
    promotion_ids,
    previous_runtime_hash,
    status,
    lease_owner,
    lease_expires_at,
    revision_id,
    created_at,
    updated_at,
    completed_at
"""


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

    async def approve_promotion_candidate(
        self,
        *,
        promotion_id: str,
        run_id: str,
        project_id: str,
        reviewed_at: datetime,
    ) -> WorkbenchRagEvalPromotionCandidateDetails:
        return await self._review_promotion_candidate(
            promotion_id=promotion_id,
            run_id=run_id,
            project_id=project_id,
            requested_status=WorkbenchRagEvalPromotionStatus.APPROVED,
            reviewed_at=reviewed_at,
            review_reason=None,
        )

    async def reject_promotion_candidate(
        self,
        *,
        promotion_id: str,
        run_id: str,
        project_id: str,
        reviewed_at: datetime,
        reason: str,
    ) -> WorkbenchRagEvalPromotionCandidateDetails:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("reason must be non-empty")
        return await self._review_promotion_candidate(
            promotion_id=promotion_id,
            run_id=run_id,
            project_id=project_id,
            requested_status=WorkbenchRagEvalPromotionStatus.REJECTED,
            reviewed_at=reviewed_at,
            review_reason=normalized_reason,
        )

    async def _review_promotion_candidate(
        self,
        *,
        promotion_id: str,
        run_id: str,
        project_id: str,
        requested_status: WorkbenchRagEvalPromotionStatus,
        reviewed_at: datetime,
        review_reason: str | None,
    ) -> WorkbenchRagEvalPromotionCandidateDetails:
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_FOR_REVIEW_SQL,
                    promotion_id,
                    run_id,
                    project_id,
                )
                if row is None:
                    raise WorkbenchRagEvalPromotionCandidateNotFoundError(
                        "Promotion candidate not found in specified run/project"
                    )

                candidate = _promotion_candidate_from_row(row)

                try:
                    transition = (
                        WorkbenchRagEvalPromotionReviewTransitionPolicy().transition(
                            current_status=candidate.status,
                            requested_status=requested_status,
                        )
                    )
                except WorkbenchRagEvalPromotionReviewTransitionConflictError as exc:
                    raise WorkbenchRagEvalPromotionCandidateConflictError(
                        str(exc)
                    ) from exc

                if not transition.changed:
                    return candidate

                updated = await connection.fetchrow(
                    """
                    UPDATE knowledge_workbench_rag_eval_promoted_questions
                    SET status = $4,
                        reviewed_at = $5,
                        review_reason = $6
                    WHERE promotion_id = $1
                      AND run_id = $2
                      AND project_id = $3::uuid
                    RETURNING
                    """
                    + WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATE_COLUMNS_SQL,
                    promotion_id,
                    run_id,
                    project_id,
                    requested_status.value,
                    reviewed_at,
                    review_reason,
                )
                if updated is None:
                    raise RuntimeError(
                        "Promotion candidate changed during locked review transition"
                    )
                return _promotion_candidate_from_row(updated)

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
        requested_ids = tuple(dict.fromkeys(promotion_ids))
        if not requested_ids:
            return ()
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_BY_IDS_SQL,
                project_id,
                list(requested_ids),
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

    async def load_promotion_application_group(
        self,
        *,
        project_id: str,
        promotion_ids: Sequence[str],
        target_runtime_entry_id: str,
        embedding_model_id: str,
    ) -> WorkbenchRagEvalPromotionApplicationSnapshot | None:
        requested_ids = tuple(sorted(dict.fromkeys(promotion_ids)))
        if not requested_ids:
            raise ValueError("promotion_ids must be non-empty")
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL,
                project_id,
                list(requested_ids),
                target_runtime_entry_id,
                embedding_model_id,
            )
        if not rows:
            return None
        if len(rows) != len(requested_ids):
            raise WorkbenchRagEvalPromotionNotFoundError(
                "Promotion application group changed while loading snapshot"
            )
        return _promotion_application_snapshot_from_rows(
            rows,
            expected_embedding_model_id=embedding_model_id,
        )

    async def get_active_embedding_revision(
        self,
        *,
        project_id: str,
        runtime_entry_id: str,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel | None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                WORKBENCH_RAG_EVAL_ACTIVE_EMBEDDING_REVISION_SQL,
                project_id,
                runtime_entry_id,
            )
        return _embedding_revision_read_model_from_row(row) if row is not None else None

    async def find_pending_revision_for_promotions(
        self,
        *,
        project_id: str,
        runtime_entry_id: str,
        source_rag_eval_run_id: str,
        promotion_ids: Sequence[str],
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel | None:
        requested_ids = tuple(sorted(dict.fromkeys(promotion_ids)))
        if not requested_ids:
            raise ValueError("promotion_ids must be non-empty")
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                WORKBENCH_RAG_EVAL_PENDING_REVISION_FOR_PROMOTIONS_SQL,
                project_id,
                runtime_entry_id,
                source_rag_eval_run_id,
                _json_text_list(requested_ids),
            )
        return _embedding_revision_read_model_from_row(row) if row is not None else None

    async def claim_promotion_application(
        self,
        *,
        application_key: str,
        project_id: str,
        runtime_entry_id: str,
        source_rag_eval_run_id: str,
        promotion_ids: Sequence[str],
        previous_runtime_hash: str,
        lease_owner: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplicationClaimDecision:
        requested_ids = tuple(sorted(dict.fromkeys(promotion_ids)))
        if not requested_ids:
            raise ValueError("promotion_ids must be non-empty")
        expected_key = stable_promotion_application_key(
            project_id=project_id,
            runtime_entry_id=runtime_entry_id,
            source_rag_eval_run_id=source_rag_eval_run_id,
            promotion_ids=requested_ids,
            previous_runtime_hash=previous_runtime_hash,
        )
        if application_key != expected_key:
            raise ValueError(
                "application_key does not match stable application identity"
            )
        if lease_expires_at <= now:
            raise ValueError("lease_expires_at must be later than now")

        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"rag-eval-application-claim:{project_id}:{runtime_entry_id}",
                )
                revision_row = await connection.fetchrow(
                    "SELECT "
                    + WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_COLUMNS_SQL
                    + """
                    FROM knowledge_workbench_rag_eval_embedding_revisions
                    WHERE application_key = $1
                    """,
                    application_key,
                )
                claim_row = await connection.fetchrow(
                    "SELECT "
                    + WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL
                    + """
                    FROM knowledge_workbench_rag_eval_promotion_application_claims
                    WHERE application_key = $1
                    FOR UPDATE
                    """,
                    application_key,
                )

                if revision_row is not None:
                    revision = _embedding_revision_read_model_from_row(revision_row)
                    if claim_row is None:
                        raise RuntimeError(
                            "embedding revision exists without promotion application claim"
                        )
                    completed = await connection.fetchrow(
                        """
                        UPDATE knowledge_workbench_rag_eval_promotion_application_claims
                        SET status = 'COMPLETED',
                            revision_id = $2,
                            updated_at = $3,
                            completed_at = $3
                        WHERE application_key = $1
                          AND lease_owner = $4
                        RETURNING
                        """
                        + WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL,
                        application_key,
                        revision.revision_id,
                        now,
                        _text_from_row(claim_row, "lease_owner"),
                    )
                    if completed is None:
                        raise RuntimeError(
                            "failed to repair completed application claim"
                        )
                    return WorkbenchRagEvalPromotionApplicationClaimDecision(
                        code=(
                            WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ALREADY_COMPLETED
                        ),
                        claim=_promotion_application_claim_from_row(completed),
                        revision=revision,
                    )

                if claim_row is not None:
                    existing = _promotion_application_claim_from_row(claim_row)
                    _assert_claim_identity(
                        claim=existing,
                        project_id=project_id,
                        runtime_entry_id=runtime_entry_id,
                        source_rag_eval_run_id=source_rag_eval_run_id,
                        promotion_ids=requested_ids,
                        previous_runtime_hash=previous_runtime_hash,
                    )
                    if (
                        existing.status
                        is WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED
                    ):
                        if existing.revision_id is None:
                            raise RuntimeError("completed claim is missing revision_id")
                        completed_revision = await _load_embedding_revision_by_id(
                            connection,
                            existing.revision_id,
                        )
                        if completed_revision is None:
                            raise RuntimeError(
                                "completed claim revision_id did not resolve to revision row"
                            )
                        return WorkbenchRagEvalPromotionApplicationClaimDecision(
                            code=(
                                WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ALREADY_COMPLETED
                            ),
                            claim=existing,
                            revision=completed_revision,
                        )
                    if (
                        existing.status
                        is WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
                        and existing.lease_expires_at > now
                    ):
                        return WorkbenchRagEvalPromotionApplicationClaimDecision(
                            code=(
                                WorkbenchRagEvalPromotionApplicationClaimDecisionCode.IN_PROGRESS
                            ),
                            claim=existing,
                        )
                    recovered = await connection.fetchrow(
                        """
                        UPDATE knowledge_workbench_rag_eval_promotion_application_claims
                        SET status = 'PREPARING',
                            lease_owner = $2,
                            lease_expires_at = $3,
                            revision_id = NULL,
                            updated_at = $4,
                            completed_at = NULL
                        WHERE application_key = $1
                          AND lease_owner = $5
                          AND status = $6
                          AND (status = 'FAILED' OR lease_expires_at <= $4)
                        RETURNING
                        """
                        + WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL,
                        application_key,
                        lease_owner,
                        lease_expires_at,
                        now,
                        existing.lease_owner,
                        existing.status.value,
                    )
                    if recovered is None:
                        raise RuntimeError(
                            "failed to acquire existing application claim"
                        )
                    code = (
                        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.RECOVERED_EXPIRED_LEASE
                        if existing.status
                        is WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
                        else WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED
                    )
                    return WorkbenchRagEvalPromotionApplicationClaimDecision(
                        code=code,
                        claim=_promotion_application_claim_from_row(recovered),
                    )

                active_row = await connection.fetchrow(
                    "SELECT "
                    + WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL
                    + """
                    FROM knowledge_workbench_rag_eval_promotion_application_claims
                    WHERE project_id = $1::uuid
                      AND runtime_entry_id = $2
                      AND status = 'PREPARING'
                    FOR UPDATE
                    """,
                    project_id,
                    runtime_entry_id,
                )
                if active_row is not None:
                    return WorkbenchRagEvalPromotionApplicationClaimDecision(
                        code=(
                            WorkbenchRagEvalPromotionApplicationClaimDecisionCode.CONFLICTING_ACTIVE_GROUP
                        ),
                        claim=_promotion_application_claim_from_row(active_row),
                    )

                inserted = await connection.fetchrow(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_promotion_application_claims (
                        application_key,
                        project_id,
                        runtime_entry_id,
                        source_rag_eval_run_id,
                        promotion_ids,
                        previous_runtime_hash,
                        status,
                        lease_owner,
                        lease_expires_at,
                        revision_id,
                        created_at,
                        updated_at,
                        completed_at
                    )
                    VALUES (
                        $1, $2::uuid, $3, $4, $5::jsonb, $6,
                        'PREPARING', $7, $8, NULL, $9, $9, NULL
                    )
                    RETURNING
                    """
                    + WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL,
                    application_key,
                    project_id,
                    runtime_entry_id,
                    source_rag_eval_run_id,
                    _json_text_list(requested_ids),
                    previous_runtime_hash,
                    lease_owner,
                    lease_expires_at,
                    now,
                )
                if inserted is None:
                    raise RuntimeError("failed to insert application claim")
                return WorkbenchRagEvalPromotionApplicationClaimDecision(
                    code=WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED,
                    claim=_promotion_application_claim_from_row(inserted),
                )

    async def fail_promotion_application_claim(
        self,
        *,
        application_key: str,
        lease_owner: str,
        failed_at: datetime,
    ) -> None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                """
                UPDATE knowledge_workbench_rag_eval_promotion_application_claims
                SET status = 'FAILED',
                    lease_expires_at = $3,
                    revision_id = NULL,
                    updated_at = $3,
                    completed_at = NULL
                WHERE application_key = $1
                  AND lease_owner = $2
                  AND status = 'PREPARING'
                  AND lease_expires_at > CURRENT_TIMESTAMP
                RETURNING application_key
                """,
                application_key,
                lease_owner,
                failed_at,
            )
        if row is None:
            raise WorkbenchRagEvalPromotionConflictError(
                "promotion application lease is no longer owned by caller",
                code=WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
            )

    async def get_embedding_revision(
        self,
        *,
        revision_id: str,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel | None:
        async with _connection(self._connection_or_pool) as connection:
            return await _load_embedding_revision_by_id(connection, revision_id)

    async def persist_promotion_application_revision(
        self,
        *,
        snapshot: WorkbenchRagEvalPromotionApplicationSnapshot,
        revision: WorkbenchRagEvalEmbeddingRevision,
        application_key: str,
        lease_owner: str,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        _assert_revision_matches_snapshot(snapshot=snapshot, revision=revision)
        expected_application_key = stable_promotion_application_key(
            project_id=revision.project_id,
            runtime_entry_id=revision.runtime_entry_id,
            source_rag_eval_run_id=revision.source_rag_eval_run_id,
            promotion_ids=revision.promotion_ids,
            previous_runtime_hash=revision.previous_runtime_hash,
        )
        if application_key != expected_application_key:
            raise ValueError("application_key does not match revision identity")
        requested_ids = tuple(sorted(revision.promotion_ids))
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"rag-eval-revision:{revision.project_id}:{revision.runtime_entry_id}",
                )
                claim_row = await connection.fetchrow(
                    "SELECT "
                    + WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_CLAIM_COLUMNS_SQL
                    + ", lease_expires_at > CURRENT_TIMESTAMP AS lease_is_active"
                    + """
                    FROM knowledge_workbench_rag_eval_promotion_application_claims
                    WHERE application_key = $1
                    FOR UPDATE
                    """,
                    application_key,
                )
                if claim_row is None:
                    raise WorkbenchRagEvalPromotionConflictError(
                        "promotion application claim not found",
                        code=WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                claim = _promotion_application_claim_from_row(claim_row)
                _assert_claim_identity(
                    claim=claim,
                    project_id=revision.project_id,
                    runtime_entry_id=revision.runtime_entry_id,
                    source_rag_eval_run_id=revision.source_rag_eval_run_id,
                    promotion_ids=requested_ids,
                    previous_runtime_hash=revision.previous_runtime_hash,
                )
                if (
                    claim.status
                    is not WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
                    or claim.lease_owner != lease_owner
                    or claim_row.get("lease_is_active") is not True
                ):
                    raise WorkbenchRagEvalPromotionConflictError(
                        "promotion application lease is no longer active for caller",
                        code=WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )

                rows = await connection.fetch(
                    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_FOR_UPDATE_SQL,
                    revision.project_id,
                    list(requested_ids),
                    revision.runtime_entry_id,
                    revision.embedding_model_id,
                )
                if len(rows) != len(requested_ids):
                    raise WorkbenchRagEvalPromotionNotFoundError(
                        "Promotion application group changed before persistence"
                    )
                locked_snapshot = _promotion_application_snapshot_from_rows(
                    rows,
                    expected_embedding_model_id=revision.embedding_model_id,
                )

                # active revision guard
                if locked_snapshot.active_revision_id is not None:
                    if locked_snapshot.active_revision_id == revision.revision_id:
                        existing = await _load_embedding_revision_by_id(
                            connection,
                            revision.revision_id,
                        )
                        if existing is None:
                            raise RuntimeError(
                                "active revision id did not resolve to revision row"
                            )
                        return existing
                    raise WorkbenchRagEvalPromotionConflictError(
                        "active PENDING_VERIFICATION revision already exists",
                        code=WorkbenchRagEvalPromotionConflictCode.ACTIVE_REVISION,
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )

                if locked_snapshot.runtime_status != "active":
                    raise WorkbenchRagEvalPromotionConflictError(
                        "runtime entry is no longer active",
                        code=WorkbenchRagEvalPromotionConflictCode.TARGET_NOT_ACTIVE,
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                if locked_snapshot.runtime_visibility != "published":
                    raise WorkbenchRagEvalPromotionConflictError(
                        "runtime entry is no longer published",
                        code=WorkbenchRagEvalPromotionConflictCode.TARGET_NOT_PUBLISHED,
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                if any(
                    candidate.status is not WorkbenchRagEvalPromotionStatus.APPROVED
                    for candidate in locked_snapshot.candidates
                ):
                    raise WorkbenchRagEvalPromotionConflictError(
                        "all promotions must still be APPROVED",
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.NON_APPROVED_CANDIDATE
                        ),
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                if (
                    locked_snapshot.runtime_hash != snapshot.runtime_hash
                    or locked_snapshot.runtime_hash != revision.previous_runtime_hash
                ):
                    raise WorkbenchRagEvalPromotionConflictError(
                        "stale runtime snapshot",
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT
                        ),
                        promotion_ids=requested_ids,
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                _assert_locked_candidates_match(
                    expected=snapshot,
                    locked=locked_snapshot,
                )

                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_embedding_revisions (
                        revision_id,
                        application_key,
                        project_id,
                        runtime_entry_id,
                        source_rag_eval_run_id,
                        promotion_ids,
                        status,
                        previous_embedding_text,
                        new_embedding_text,
                        previous_embedding,
                        new_embedding,
                        previous_promoted_questions,
                        new_promoted_questions,
                        embedding_model_id,
                        embedding_dimensions,
                        previous_runtime_hash,
                        new_runtime_hash,
                        created_at,
                        accepted_at,
                        regression_failed_at,
                        rolled_back_at
                    )
                    VALUES (
                        $1, $2, $3::uuid, $4, $5, $6::jsonb, $7,
                        $8, $9, $10::vector, $11::vector,
                        $12::jsonb, $13::jsonb, $14, $15,
                        $16, $17, $18, $19, $20, $21
                    )
                    """,
                    revision.revision_id,
                    application_key,
                    revision.project_id,
                    revision.runtime_entry_id,
                    revision.source_rag_eval_run_id,
                    _json_text_list(tuple(sorted(revision.promotion_ids))),
                    revision.status.value,
                    revision.previous_embedding_text,
                    revision.new_embedding_text,
                    _pg_vector_text(revision.previous_embedding),
                    _pg_vector_text(revision.new_embedding),
                    _json_text_list(revision.previous_promoted_questions),
                    _json_text_list(revision.new_promoted_questions),
                    revision.embedding_model_id,
                    revision.embedding_dimensions,
                    revision.previous_runtime_hash,
                    revision.new_runtime_hash,
                    revision.created_at,
                    revision.accepted_at,
                    revision.regression_failed_at,
                    revision.rolled_back_at,
                )

                runtime_update = await connection.execute(
                    """
                    UPDATE knowledge_workbench_runtime_retrieval_entries
                    SET possible_questions = $3::jsonb,
                        embedding_text = $4
                    WHERE project_id = $1::uuid
                      AND runtime_entry_id = $2
                      AND visibility = 'published'
                      AND status = 'active'
                    """,
                    revision.project_id,
                    revision.runtime_entry_id,
                    _json_text_list(revision.new_promoted_questions),
                    revision.new_embedding_text,
                )
                _require_affected_rows(
                    runtime_update,
                    expected=1,
                    operation="runtime entry update",
                )

                await connection.execute(
                    """
                    DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
                    WHERE runtime_entry_id = $1
                      AND embedding_model_id = $2
                    """,
                    revision.runtime_entry_id,
                    revision.embedding_model_id,
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings (
                        runtime_entry_id,
                        embedding_model_id,
                        dimensions,
                        embedding,
                        embedding_text_hash,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4::vector, $5, $6)
                    """,
                    revision.runtime_entry_id,
                    revision.embedding_model_id,
                    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
                    _pg_vector_text(revision.new_embedding),
                    sha256(revision.new_embedding_text.encode("utf-8")).hexdigest(),
                    revision.created_at,
                )

                promotion_update = await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_promoted_questions
                    SET status = 'applied',
                        applied_at = $4
                    WHERE project_id = $1::uuid
                      AND promotion_id = ANY($2::text[])
                      AND target_runtime_entry_id = $3
                      AND status = 'approved'
                    """,
                    revision.project_id,
                    list(requested_ids),
                    revision.runtime_entry_id,
                    revision.created_at,
                )
                _require_affected_rows(
                    promotion_update,
                    expected=len(requested_ids),
                    operation="promotion status update",
                )

                run_update = await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_runs
                    SET status = 'verifying',
                        current_phase = 'post_promotion_verification',
                        updated_at = $3
                    WHERE run_id = $1
                      AND project_id = $2::uuid
                      AND status IN ('promotion_review', 'verifying')
                    """,
                    revision.source_rag_eval_run_id,
                    revision.project_id,
                    revision.created_at,
                )
                _require_affected_rows(
                    run_update,
                    expected=1,
                    operation="RAG Eval run transition",
                )

                event_payload = {
                    "workflow_run_id": revision.source_rag_eval_run_id,
                    "rag_eval_run_id": revision.source_rag_eval_run_id,
                    "project_id": revision.project_id,
                    "runtime_entry_id": revision.runtime_entry_id,
                    "revision_id": revision.revision_id,
                    "application_key": application_key,
                    "promotion_ids": list(requested_ids),
                    "status": revision.status.value,
                    "phase": "POST_PROMOTION_VERIFICATION",
                }
                await _append_promotion_revision_event(
                    connection,
                    event_type=WorkbenchRagEvalWorkflowEventType.PROMOTIONS_APPLIED.value,
                    message="RAG Eval promotions applied",
                    payload=event_payload,
                    revision=revision,
                )
                await _append_promotion_revision_event(
                    connection,
                    event_type=WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_CREATED.value,
                    message="RAG Eval embedding revision created",
                    payload=event_payload,
                    revision=revision,
                )
                await connection.execute(
                    """
                    INSERT INTO workflow_runtime_command_log (
                        command_id,
                        command_type,
                        workflow_run_id,
                        idempotency_key,
                        payload,
                        status,
                        run_after,
                        created_at,
                        updated_at,
                        causation_event_id,
                        correlation_id,
                        attempt_count
                    )
                    VALUES (
                        $1, $2, $3, $4, $5::jsonb, 'PENDING',
                        $6, $6, $6, NULL, $7, 0
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    """,
                    (
                        "workflow-command:"
                        f"{revision.source_rag_eval_run_id}:"
                        f"post-promotion-verification:{revision.revision_id}"
                    ),
                    (
                        WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION.value
                    ),
                    revision.source_rag_eval_run_id,
                    (f"rag-eval-post-promotion-verification:{revision.revision_id}"),
                    json.dumps(
                        {
                            "workflow_family": "workbench_rag_eval",
                            "workflow_run_id": revision.source_rag_eval_run_id,
                            "rag_eval_run_id": revision.source_rag_eval_run_id,
                            "project_id": revision.project_id,
                            "revision_id": revision.revision_id,
                            "runtime_entry_id": revision.runtime_entry_id,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    revision.created_at,
                    revision.revision_id,
                )

                claim_completion = await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_promotion_application_claims
                    SET status = 'COMPLETED',
                        revision_id = $3,
                        updated_at = $4,
                        completed_at = $4
                    WHERE application_key = $1
                      AND lease_owner = $2
                      AND status = 'PREPARING'
                      AND lease_expires_at > CURRENT_TIMESTAMP
                    """,
                    application_key,
                    lease_owner,
                    revision.revision_id,
                    revision.created_at,
                )
                _require_affected_rows(
                    claim_completion,
                    expected=1,
                    operation="promotion application claim completion",
                )

        return _embedding_revision_read_model(revision)

    async def list_embedding_revisions(
        self,
        *,
        project_id: str,
        source_rag_eval_run_id: str,
    ) -> tuple[WorkbenchRagEvalEmbeddingRevisionReadModel, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                "SELECT "
                + WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_COLUMNS_SQL
                + """
                FROM knowledge_workbench_rag_eval_embedding_revisions
                WHERE project_id = $1::uuid
                  AND source_rag_eval_run_id = $2
                ORDER BY created_at, revision_id
                """,
                project_id,
                source_rag_eval_run_id,
            )
        return tuple(_embedding_revision_read_model_from_row(row) for row in rows)

    async def list_post_promotion_verifications(
        self,
        *,
        project_id: str,
        source_rag_eval_run_id: str,
    ) -> tuple[WorkbenchRagEvalVerificationReadModel, ...]:
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                _VERIFICATION_READ_SQL
                + """
                WHERE verification.project_id = $1::uuid
                  AND verification.source_rag_eval_run_id = $2
                GROUP BY verification.verification_id
                ORDER BY verification.created_at, verification.verification_id
                """,
                project_id,
                source_rag_eval_run_id,
            )
        return tuple(_verification_read_model_from_row(row) for row in rows)

    async def get_post_promotion_verification(
        self,
        *,
        project_id: str,
        revision_id: str,
    ) -> WorkbenchRagEvalVerificationReadModel | None:
        async with _connection(self._connection_or_pool) as connection:
            row = await connection.fetchrow(
                _VERIFICATION_READ_SQL
                + """
                WHERE verification.project_id = $1::uuid
                  AND verification.revision_id = $2
                GROUP BY verification.verification_id
                """,
                project_id,
                revision_id,
            )
        return _verification_read_model_from_row(row) if row is not None else None

    async def get_embedding_revision_for_verification(
        self,
        *,
        project_id: str,
        revision_id: str,
    ) -> WorkbenchRagEvalEmbeddingRevision:
        async with _connection(self._connection_or_pool) as connection:
            return await _load_embedding_revision_full_for_update(
                connection,
                revision_id,
                project_id,
            )

    async def start_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        started_at: datetime,
    ) -> int:
        verification_id = _verification_id(revision.revision_id)
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_rag_eval_verifications (
                        verification_id,
                        revision_id,
                        project_id,
                        source_rag_eval_run_id,
                        runtime_entry_id,
                        status,
                        policy_version,
                        created_at
                    )
                    VALUES ($1, $2, $3::uuid, $4, $5, 'running', $6, $7)
                    ON CONFLICT (revision_id) DO UPDATE
                    SET status = CASE
                            WHEN knowledge_workbench_rag_eval_verifications.status
                                 IN ('pending', 'running')
                            THEN 'running'
                            ELSE knowledge_workbench_rag_eval_verifications.status
                        END
                    """,
                    verification_id,
                    revision.revision_id,
                    revision.project_id,
                    revision.source_rag_eval_run_id,
                    revision.runtime_entry_id,
                    WORKBENCH_RAG_EVAL_VERIFICATION_POLICY_VERSION,
                    started_at,
                )
                rows = await _verification_query_plan_rows(
                    connection,
                    revision=revision,
                )
                for row in rows:
                    await connection.execute(
                        """
                        INSERT INTO knowledge_workbench_rag_eval_verification_queries (
                            verification_query_id,
                            verification_id,
                            revision_id,
                            source_rag_eval_run_id,
                            project_id,
                            question_id,
                            promotion_id,
                            query_text,
                            dataset_role,
                            expected_runtime_entry_id,
                            expected_fact_id,
                            source_runtime_entry_id,
                            source_outcome_id,
                            created_at
                        )
                        VALUES (
                            $1, $2, $3, $4, $5::uuid, $6, $7, $8, $9,
                            $10, $11, $12, $13, $14
                        )
                        ON CONFLICT (verification_query_id) DO NOTHING
                        """,
                        _verification_query_id(
                            verification_id=verification_id,
                            dataset_role=_text_from_row(row, "dataset_role"),
                            query_text=_text_from_row(row, "query_text"),
                            expected_runtime_entry_id=_text_from_row(
                                row,
                                "expected_runtime_entry_id",
                            ),
                        ),
                        verification_id,
                        revision.revision_id,
                        revision.source_rag_eval_run_id,
                        revision.project_id,
                        _optional_text_from_row(row, "question_id"),
                        _optional_text_from_row(row, "promotion_id"),
                        _text_from_row(row, "query_text"),
                        _text_from_row(row, "dataset_role"),
                        _text_from_row(row, "expected_runtime_entry_id"),
                        _text_from_row(row, "expected_fact_id"),
                        _text_from_row(row, "source_runtime_entry_id"),
                        _optional_text_from_row(row, "source_outcome_id"),
                        started_at,
                    )
                total_query_count = await connection.fetchval(
                    """
                    SELECT count(*)::int
                    FROM knowledge_workbench_rag_eval_verification_queries
                    WHERE verification_id = $1
                    """,
                    verification_id,
                )
        return int(total_query_count or 0)

    async def list_pending_post_promotion_verification_queries(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        limit: int,
    ) -> tuple[WorkbenchRagEvalVerificationQuery, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        verification_id = _verification_id(revision.revision_id)
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                SELECT
                    query.verification_query_id,
                    query.revision_id,
                    query.source_rag_eval_run_id AS run_id,
                    query.project_id::text AS project_id,
                    query.query_text,
                    query.dataset_role,
                    query.expected_runtime_entry_id,
                    query.expected_fact_id,
                    query.source_runtime_entry_id,
                    query.question_id,
                    query.source_outcome_id,
                    query.promotion_id,
                    query.created_at
                FROM knowledge_workbench_rag_eval_verification_queries AS query
                LEFT JOIN knowledge_workbench_rag_eval_verification_outcomes AS outcome
                  ON outcome.verification_query_id = query.verification_query_id
                WHERE query.verification_id = $1
                  AND outcome.verification_outcome_id IS NULL
                ORDER BY query.dataset_role, query.created_at, query.verification_query_id
                LIMIT $2
                """,
                verification_id,
                limit,
            )
        return tuple(_verification_query_from_row(row) for row in rows)

    async def observe_post_promotion_verification_query(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        query: WorkbenchRagEvalVerificationQuery,
        query_embedding: tuple[float, ...],
        use_new_embedding: bool,
        limit: int,
    ) -> WorkbenchRagEvalVerificationSearchObservation:
        override_embedding = (
            revision.new_embedding if use_new_embedding else revision.previous_embedding
        )
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                WITH ranked AS (
                    SELECT
                        entry.runtime_entry_id,
                        COALESCE(NULLIF(entry.fact_id, ''), entry.runtime_entry_id)
                            AS fact_id,
                        (1 - (
                            CASE
                                WHEN entry.runtime_entry_id = $2
                                THEN $5::vector
                                ELSE emb.embedding
                            END <=> $4::vector
                        )) AS score,
                        row_number() OVER (
                            ORDER BY
                                CASE
                                    WHEN entry.runtime_entry_id = $2
                                    THEN $5::vector
                                    ELSE emb.embedding
                                END <=> $4::vector,
                                entry.runtime_entry_id
                        ) AS rank
                    FROM knowledge_workbench_runtime_retrieval_entries AS entry
                    JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
                      ON emb.runtime_entry_id = entry.runtime_entry_id
                    WHERE entry.project_id = $1::uuid
                      AND entry.visibility = 'published'
                      AND entry.status = 'active'
                      AND emb.embedding_model_id = $6
                      AND emb.dimensions = $7
                )
                SELECT runtime_entry_id, fact_id, score, rank
                FROM ranked
                WHERE rank <= $8
                   OR runtime_entry_id = $3
                ORDER BY rank
                """,
                revision.project_id,
                revision.runtime_entry_id,
                query.expected_runtime_entry_id,
                _pg_vector_text(query_embedding),
                _pg_vector_text(override_embedding),
                revision.embedding_model_id,
                revision.embedding_dimensions,
                limit,
            )
        return _verification_observation_from_rows(query=query, rows=rows)

    async def persist_post_promotion_verification_outcomes(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        outcome_pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
        observed_at: datetime,
    ) -> None:
        verification_id = _verification_id(revision.revision_id)
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                for pair in outcome_pairs:
                    await connection.execute(
                        """
                        INSERT INTO knowledge_workbench_rag_eval_verification_outcomes (
                            verification_outcome_id,
                            verification_id,
                            verification_query_id,
                            revision_id,
                            project_id,
                            expected_runtime_entry_id,
                            expected_fact_id,
                            before_expected_rank,
                            before_expected_score,
                            before_best_competitor_runtime_entry_id,
                            before_best_competitor_fact_id,
                            before_best_competitor_score,
                            before_score_margin,
                            before_classification,
                            after_expected_rank,
                            after_expected_score,
                            after_best_competitor_runtime_entry_id,
                            after_best_competitor_fact_id,
                            after_best_competitor_score,
                            after_score_margin,
                            after_classification,
                            created_at
                        )
                        SELECT
                            $1, $2, query.verification_query_id, $3,
                            query.project_id, query.expected_runtime_entry_id,
                            query.expected_fact_id, $4, $5, $6, NULL, NULL,
                            $7, $8, $9, $10, $11, NULL, NULL, $12, $13, $14
                        FROM knowledge_workbench_rag_eval_verification_queries AS query
                        WHERE query.verification_query_id = $15
                        ON CONFLICT (verification_query_id) DO UPDATE
                        SET before_expected_rank = EXCLUDED.before_expected_rank,
                            before_expected_score = EXCLUDED.before_expected_score,
                            before_best_competitor_runtime_entry_id =
                                EXCLUDED.before_best_competitor_runtime_entry_id,
                            before_score_margin = EXCLUDED.before_score_margin,
                            before_classification = EXCLUDED.before_classification,
                            after_expected_rank = EXCLUDED.after_expected_rank,
                            after_expected_score = EXCLUDED.after_expected_score,
                            after_best_competitor_runtime_entry_id =
                                EXCLUDED.after_best_competitor_runtime_entry_id,
                            after_score_margin = EXCLUDED.after_score_margin,
                            after_classification = EXCLUDED.after_classification
                        """,
                        _verification_outcome_id(pair.verification_query_id),
                        verification_id,
                        revision.revision_id,
                        pair.before_expected_rank,
                        pair.before_expected_score,
                        pair.before_best_competitor_runtime_entry_id,
                        pair.before_score_margin,
                        pair.before_classification.value,
                        pair.after_expected_rank,
                        pair.after_expected_score,
                        pair.after_best_competitor_runtime_entry_id,
                        pair.after_score_margin,
                        pair.after_classification.value,
                        observed_at,
                        pair.verification_query_id,
                    )

    async def count_remaining_post_promotion_verification_queries(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> int:
        verification_id = _verification_id(revision.revision_id)
        async with _connection(self._connection_or_pool) as connection:
            remaining = await connection.fetchval(
                """
                SELECT count(*)::int
                FROM knowledge_workbench_rag_eval_verification_queries AS query
                LEFT JOIN knowledge_workbench_rag_eval_verification_outcomes AS outcome
                  ON outcome.verification_query_id = query.verification_query_id
                WHERE query.verification_id = $1
                  AND outcome.verification_outcome_id IS NULL
                """,
                verification_id,
            )
        return int(remaining or 0)

    async def list_post_promotion_verification_outcome_pairs(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> tuple[WorkbenchRagEvalVerificationOutcomePair, ...]:
        verification_id = _verification_id(revision.revision_id)
        async with _connection(self._connection_or_pool) as connection:
            rows = await connection.fetch(
                """
                SELECT
                    query.verification_query_id,
                    query.dataset_role,
                    query.expected_runtime_entry_id,
                    outcome.before_expected_rank,
                    outcome.after_expected_rank,
                    outcome.before_expected_score,
                    outcome.after_expected_score,
                    outcome.before_best_competitor_runtime_entry_id,
                    outcome.after_best_competitor_runtime_entry_id,
                    outcome.before_score_margin,
                    outcome.after_score_margin,
                    outcome.before_classification,
                    outcome.after_classification
                FROM knowledge_workbench_rag_eval_verification_outcomes AS outcome
                JOIN knowledge_workbench_rag_eval_verification_queries AS query
                  ON query.verification_query_id = outcome.verification_query_id
                WHERE outcome.verification_id = $1
                ORDER BY query.dataset_role, query.created_at, query.verification_query_id
                """,
                verification_id,
            )
        return tuple(_verification_outcome_pair_from_row(row) for row in rows)

    async def complete_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        metrics: WorkbenchRagEvalVerificationMetrics,
        policy_decision: WorkbenchRagEvalVerificationPolicyDecision,
        completed_at: datetime,
    ) -> None:
        verification_id = _verification_id(revision.revision_id)
        status = (
            WorkbenchRagEvalVerificationStatus.PASSED
            if policy_decision.decision
            is WorkbenchRagEvalVerificationDecision.ACCEPTABLE
            else WorkbenchRagEvalVerificationStatus.REGRESSION_FAILED
        )
        revision_status = (
            WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
            if status is WorkbenchRagEvalVerificationStatus.PASSED
            else WorkbenchRagEvalEmbeddingRevisionStatus.REGRESSION_FAILED
        )
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_verifications
                    SET status = $2,
                        decision = $3,
                        failure_reasons = $4::jsonb,
                        metrics = $5::jsonb,
                        completed_at = $6
                    WHERE verification_id = $1
                      AND status IN ('pending', 'running')
                    """,
                    verification_id,
                    status.value,
                    policy_decision.decision.value,
                    json.dumps(
                        [reason.value for reason in policy_decision.failure_reasons],
                        ensure_ascii=False,
                    ),
                    json.dumps(metrics.to_json_dict(), ensure_ascii=False),
                    completed_at,
                )
                await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_embedding_revisions
                    SET status = $3,
                        regression_failed_at = CASE
                            WHEN $3 = 'regression_failed' THEN $4
                            ELSE regression_failed_at
                        END
                    WHERE project_id = $1::uuid
                      AND revision_id = $2
                      AND status = 'pending_verification'
                    """,
                    revision.project_id,
                    revision.revision_id,
                    revision_status.value,
                    completed_at,
                )
                if status is WorkbenchRagEvalVerificationStatus.REGRESSION_FAILED:
                    await connection.execute(
                        """
                        UPDATE knowledge_workbench_rag_eval_promoted_questions
                        SET status = 'regression_failed'
                        WHERE project_id = $1::uuid
                          AND promotion_id = ANY($2::text[])
                          AND status = 'applied'
                        """,
                        revision.project_id,
                        list(revision.promotion_ids),
                    )

    async def fail_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        error_message: str,
    ) -> None:
        verification_id = _verification_id(revision.revision_id)
        async with _connection(self._connection_or_pool) as connection:
            await connection.execute(
                """
                UPDATE knowledge_workbench_rag_eval_verifications
                SET status = 'failed',
                    failed_at = $2,
                    error_message = $3
                WHERE verification_id = $1
                  AND status IN ('pending', 'running')
                """,
                verification_id,
                revision.created_at,
                error_message.strip() or "post-promotion verification failed",
            )

    async def accept_embedding_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        accepted_at: datetime,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                revision = await _load_embedding_revision_full_for_update(
                    connection,
                    revision_id,
                    project_id,
                )
                if revision.status is WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED:
                    return _embedding_revision_read_model(revision)
                if (
                    revision.status
                    is not WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
                ):
                    raise WorkbenchRagEvalPromotionConflictError(
                        "only PENDING_VERIFICATION revision can be accepted",
                        code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
                        promotion_ids=tuple(sorted(revision.promotion_ids)),
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                verification_row = await connection.fetchrow(
                    """
                    SELECT verification_id
                    FROM knowledge_workbench_rag_eval_verifications
                    WHERE revision_id = $1
                      AND project_id = $2::uuid
                      AND status = 'passed'
                      AND decision = 'acceptable'
                    """,
                    revision.revision_id,
                    revision.project_id,
                )
                if verification_row is None:
                    raise WorkbenchRagEvalPromotionConflictError(
                        "revision requires passed verification before accept",
                        code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
                        promotion_ids=tuple(sorted(revision.promotion_ids)),
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                update = await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_embedding_revisions
                    SET status = 'accepted',
                        accepted_at = $3
                    WHERE revision_id = $1
                      AND project_id = $2::uuid
                      AND status = 'pending_verification'
                    """,
                    revision.revision_id,
                    revision.project_id,
                    accepted_at,
                )
                _require_affected_rows(
                    update,
                    expected=1,
                    operation="embedding revision accept",
                )
                accepted = WorkbenchRagEvalEmbeddingRevision(
                    revision_id=revision.revision_id,
                    project_id=revision.project_id,
                    runtime_entry_id=revision.runtime_entry_id,
                    source_rag_eval_run_id=revision.source_rag_eval_run_id,
                    promotion_ids=revision.promotion_ids,
                    status=WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED,
                    previous_embedding_text=revision.previous_embedding_text,
                    new_embedding_text=revision.new_embedding_text,
                    previous_embedding=revision.previous_embedding,
                    new_embedding=revision.new_embedding,
                    previous_promoted_questions=revision.previous_promoted_questions,
                    new_promoted_questions=revision.new_promoted_questions,
                    embedding_model_id=revision.embedding_model_id,
                    embedding_dimensions=revision.embedding_dimensions,
                    previous_runtime_hash=revision.previous_runtime_hash,
                    new_runtime_hash=revision.new_runtime_hash,
                    created_at=accepted_at,
                    accepted_at=accepted_at,
                    regression_failed_at=None,
                    rolled_back_at=None,
                )
                await _append_promotion_revision_event(
                    connection,
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_ACCEPTED.value
                    ),
                    message="RAG Eval embedding revision accepted",
                    payload={
                        "workflow_run_id": revision.source_rag_eval_run_id,
                        "rag_eval_run_id": revision.source_rag_eval_run_id,
                        "project_id": revision.project_id,
                        "runtime_entry_id": revision.runtime_entry_id,
                        "revision_id": revision.revision_id,
                        "promotion_ids": list(sorted(revision.promotion_ids)),
                        "status": "accepted",
                    },
                    revision=accepted,
                )
                return _embedding_revision_read_model(accepted)

    async def rollback_embedding_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        rolled_back_at: datetime,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        async with _connection(self._connection_or_pool) as connection:
            async with connection.transaction():
                revision = await _load_embedding_revision_full_for_update(
                    connection,
                    revision_id,
                    project_id,
                )
                if (
                    revision.status
                    is WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK
                ):
                    return _embedding_revision_read_model(revision)
                if revision.status is WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED:
                    raise WorkbenchRagEvalPromotionConflictError(
                        "ACCEPTED revision cannot be rolled back",
                        code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
                        promotion_ids=tuple(sorted(revision.promotion_ids)),
                        runtime_entry_id=revision.runtime_entry_id,
                    )

                runtime_row = await connection.fetchrow(
                    """
                    SELECT
                        entry.possible_questions,
                        entry.embedding_text,
                        emb.embedding::text AS current_embedding,
                        emb.embedding_model_id,
                        emb.dimensions AS embedding_dimensions
                    FROM knowledge_workbench_runtime_retrieval_entries AS entry
                    JOIN knowledge_workbench_runtime_retrieval_entry_embeddings AS emb
                      ON emb.runtime_entry_id = entry.runtime_entry_id
                     AND emb.embedding_model_id = $3
                    WHERE entry.project_id = $1::uuid
                      AND entry.runtime_entry_id = $2
                      AND entry.visibility = 'published'
                      AND entry.status = 'active'
                    FOR UPDATE OF entry
                    """,
                    revision.project_id,
                    revision.runtime_entry_id,
                    revision.embedding_model_id,
                )
                if runtime_row is None:
                    raise WorkbenchRagEvalPromotionConflictError(
                        "runtime entry not found for rollback",
                        code=WorkbenchRagEvalPromotionConflictCode.TARGET_NOT_ACTIVE,
                        promotion_ids=tuple(sorted(revision.promotion_ids)),
                        runtime_entry_id=revision.runtime_entry_id,
                    )
                current_hash = stable_runtime_snapshot_hash(
                    possible_questions=_text_tuple(
                        runtime_row.get("possible_questions")
                    ),
                    embedding_text=_text_from_row(runtime_row, "embedding_text"),
                    embedding=_vector_tuple(runtime_row.get("current_embedding")),
                    embedding_model_id=_text_from_row(
                        runtime_row,
                        "embedding_model_id",
                    ),
                    embedding_dimensions=_int_from_row(
                        runtime_row,
                        "embedding_dimensions",
                    ),
                )
                if current_hash != revision.new_runtime_hash:
                    raise WorkbenchRagEvalPromotionConflictError(
                        "stale runtime state blocks rollback",
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT
                        ),
                        promotion_ids=tuple(sorted(revision.promotion_ids)),
                        runtime_entry_id=revision.runtime_entry_id,
                    )

                runtime_update = await connection.execute(
                    """
                    UPDATE knowledge_workbench_runtime_retrieval_entries
                    SET possible_questions = $3::jsonb,
                        embedding_text = $4
                    WHERE project_id = $1::uuid
                      AND runtime_entry_id = $2
                      AND visibility = 'published'
                      AND status = 'active'
                    """,
                    revision.project_id,
                    revision.runtime_entry_id,
                    _json_text_list(revision.previous_promoted_questions),
                    revision.previous_embedding_text,
                )
                _require_affected_rows(
                    runtime_update,
                    expected=1,
                    operation="runtime entry rollback update",
                )
                await connection.execute(
                    """
                    DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings
                    WHERE runtime_entry_id = $1
                      AND embedding_model_id = $2
                    """,
                    revision.runtime_entry_id,
                    revision.embedding_model_id,
                )
                await connection.execute(
                    """
                    INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings (
                        runtime_entry_id,
                        embedding_model_id,
                        dimensions,
                        embedding,
                        embedding_text_hash,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4::vector, $5, $6)
                    """,
                    revision.runtime_entry_id,
                    revision.embedding_model_id,
                    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
                    _pg_vector_text(revision.previous_embedding),
                    sha256(
                        revision.previous_embedding_text.encode("utf-8")
                    ).hexdigest(),
                    rolled_back_at,
                )
                revision_update = await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_embedding_revisions
                    SET status = 'rolled_back',
                        rolled_back_at = $3
                    WHERE revision_id = $1
                      AND project_id = $2::uuid
                      AND status IN ('pending_verification', 'regression_failed')
                    """,
                    revision.revision_id,
                    revision.project_id,
                    rolled_back_at,
                )
                _require_affected_rows(
                    revision_update,
                    expected=1,
                    operation="embedding revision rollback",
                )
                await connection.execute(
                    """
                    UPDATE knowledge_workbench_rag_eval_promoted_questions
                    SET status = 'rolled_back'
                    WHERE project_id = $1::uuid
                      AND promotion_id = ANY($2::text[])
                      AND status IN ('applied', 'regression_failed')
                    """,
                    revision.project_id,
                    list(revision.promotion_ids),
                )

                rolled_back = WorkbenchRagEvalEmbeddingRevision(
                    revision_id=revision.revision_id,
                    project_id=revision.project_id,
                    runtime_entry_id=revision.runtime_entry_id,
                    source_rag_eval_run_id=revision.source_rag_eval_run_id,
                    promotion_ids=revision.promotion_ids,
                    status=WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK,
                    previous_embedding_text=revision.previous_embedding_text,
                    new_embedding_text=revision.new_embedding_text,
                    previous_embedding=revision.previous_embedding,
                    new_embedding=revision.new_embedding,
                    previous_promoted_questions=revision.previous_promoted_questions,
                    new_promoted_questions=revision.new_promoted_questions,
                    embedding_model_id=revision.embedding_model_id,
                    embedding_dimensions=revision.embedding_dimensions,
                    previous_runtime_hash=revision.previous_runtime_hash,
                    new_runtime_hash=revision.new_runtime_hash,
                    created_at=rolled_back_at,
                    accepted_at=None,
                    regression_failed_at=revision.regression_failed_at,
                    rolled_back_at=rolled_back_at,
                )
                await _append_promotion_revision_event(
                    connection,
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_ROLLED_BACK.value
                    ),
                    message="RAG Eval embedding revision rolled back",
                    payload={
                        "workflow_run_id": revision.source_rag_eval_run_id,
                        "rag_eval_run_id": revision.source_rag_eval_run_id,
                        "project_id": revision.project_id,
                        "runtime_entry_id": revision.runtime_entry_id,
                        "revision_id": revision.revision_id,
                        "promotion_ids": list(sorted(revision.promotion_ids)),
                        "status": "rolled_back",
                    },
                    revision=rolled_back,
                )
                return _embedding_revision_read_model(rolled_back)


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


async def _verification_query_plan_rows(
    connection: WorkbenchRagEvalConnectionLike,
    *,
    revision: WorkbenchRagEvalEmbeddingRevision,
) -> tuple[Mapping[str, object], ...]:
    rows = await connection.fetch(
        """
        SELECT
            'promoted'::text AS dataset_role,
            promotion.question_id,
            promotion.promotion_id,
            promotion.question AS query_text,
            promotion.target_runtime_entry_id AS expected_runtime_entry_id,
            promotion.target_fact_id AS expected_fact_id,
            promotion.target_runtime_entry_id AS source_runtime_entry_id,
            promotion.outcome_id AS source_outcome_id
        FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
        WHERE promotion.project_id = $1::uuid
          AND promotion.run_id = $2
          AND promotion.promotion_id = ANY($3::text[])

        UNION ALL

        SELECT
            question.evaluation_role::text AS dataset_role,
            question.question_id,
            NULL::text AS promotion_id,
            question.question AS query_text,
            question.expected_runtime_entry_id,
            question.expected_fact_id,
            question.expected_runtime_entry_id AS source_runtime_entry_id,
            outcome.outcome_id AS source_outcome_id
        FROM knowledge_workbench_rag_eval_questions AS question
        LEFT JOIN knowledge_workbench_rag_eval_retrieval_outcomes AS outcome
          ON outcome.run_id = question.run_id
         AND outcome.question_id = question.question_id
         AND outcome.evaluation_stage = 'initial'
        WHERE question.project_id = $1::uuid
          AND question.run_id = $2
          AND question.evaluation_role IN ('baseline', 'holdout')

        UNION ALL

        SELECT
            'neighbour'::text AS dataset_role,
            promotion.question_id,
            NULL::text AS promotion_id,
            promotion.question AS query_text,
            promotion.competitor_runtime_entry_id AS expected_runtime_entry_id,
            promotion.competitor_fact_id AS expected_fact_id,
            promotion.target_runtime_entry_id AS source_runtime_entry_id,
            promotion.outcome_id AS source_outcome_id
        FROM knowledge_workbench_rag_eval_promoted_questions AS promotion
        WHERE promotion.project_id = $1::uuid
          AND promotion.run_id = $2
          AND promotion.promotion_id = ANY($3::text[])
          AND promotion.competitor_runtime_entry_id IS NOT NULL
          AND promotion.competitor_fact_id IS NOT NULL
        ORDER BY dataset_role, query_text, expected_runtime_entry_id
        """,
        revision.project_id,
        revision.source_rag_eval_run_id,
        list(revision.promotion_ids),
    )
    return tuple(rows)


def _verification_observation_from_rows(
    *,
    query: WorkbenchRagEvalVerificationQuery,
    rows: Sequence[Mapping[str, object]],
) -> WorkbenchRagEvalVerificationSearchObservation:
    expected_row = next(
        (
            row
            for row in rows
            if _text_from_row(row, "runtime_entry_id")
            == query.expected_runtime_entry_id
        ),
        None,
    )
    competitor_row = next(
        (
            row
            for row in rows
            if _text_from_row(row, "runtime_entry_id")
            != query.expected_runtime_entry_id
        ),
        None,
    )
    expected_rank = (
        _int_from_row(expected_row, "rank") if expected_row is not None else None
    )
    expected_score = (
        _float_from_row(expected_row, "score") if expected_row is not None else None
    )
    competitor_score = (
        _float_from_row(competitor_row, "score") if competitor_row is not None else None
    )
    outcome = WorkbenchRagEvalRetrievalOutcomePolicy().build(
        outcome_id=_verification_outcome_id(query.verification_query_id),
        run_id=query.run_id,
        question_id=query.verification_query_id,
        project_id=query.project_id,
        evaluation_stage="verification",
        expected_runtime_entry_id=query.expected_runtime_entry_id,
        expected_fact_id=query.expected_fact_id,
        expected_rank=expected_rank,
        expected_score=expected_score,
        best_competitor_runtime_entry_id=_text_from_row(
            competitor_row,
            "runtime_entry_id",
        )
        if competitor_row is not None
        else None,
        best_competitor_fact_id=_text_from_row(competitor_row, "fact_id")
        if competitor_row is not None
        else None,
        best_competitor_score=competitor_score,
        competitor_same_document=bool(
            competitor_row is not None
            and (
                expected_rank is None
                or _int_from_row(competitor_row, "rank") < expected_rank
            )
        ),
        created_at=query.created_at,
    )
    classification = outcome.classification
    if query.dataset_role is WorkbenchRagEvalVerificationDatasetRole.BASELINE and (
        expected_rank is None or expected_rank > 3
    ):
        classification = (
            WorkbenchRagEvalRetrievalClassification.EXISTING_ALIAS_RETRIEVAL_FAILURE
        )
    return WorkbenchRagEvalVerificationSearchObservation(
        expected_rank=expected_rank,
        expected_score=expected_score,
        best_competitor_runtime_entry_id=outcome.best_competitor_runtime_entry_id,
        best_competitor_fact_id=outcome.best_competitor_fact_id,
        best_competitor_score=outcome.best_competitor_score,
        score_margin=outcome.score_margin,
        classification=classification,
    )


def _verification_read_model_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalVerificationReadModel:
    decision_text = _optional_text_from_row(row, "decision")
    return WorkbenchRagEvalVerificationReadModel(
        verification_id=_text_from_row(row, "verification_id"),
        revision_id=_text_from_row(row, "revision_id"),
        project_id=_text_from_row(row, "project_id"),
        source_rag_eval_run_id=_text_from_row(row, "source_rag_eval_run_id"),
        runtime_entry_id=_text_from_row(row, "runtime_entry_id"),
        status=WorkbenchRagEvalVerificationStatus(_text_from_row(row, "status")),
        policy_version=_text_from_row(row, "policy_version"),
        decision=WorkbenchRagEvalVerificationDecision(decision_text)
        if decision_text is not None
        else None,
        failure_reasons=tuple(
            WorkbenchRagEvalVerificationFailureReason(reason)
            for reason in _text_tuple(row.get("failure_reasons"))
        ),
        metrics=_json_object_from_row(row, "metrics"),
        query_count=_int_from_row_default_zero(row, "query_count"),
        outcome_count=_int_from_row_default_zero(row, "outcome_count"),
        created_at=_datetime_from_row(row, "created_at"),
        completed_at=_optional_datetime_from_row(row, "completed_at"),
        failed_at=_optional_datetime_from_row(row, "failed_at"),
        error_message=_optional_text_from_row(row, "error_message"),
    )


def _verification_id(revision_id: str) -> str:
    return "rag-eval-verification:" + sha256(revision_id.encode("utf-8")).hexdigest()


def _verification_query_id(
    *,
    verification_id: str,
    dataset_role: str,
    query_text: str,
    expected_runtime_entry_id: str,
) -> str:
    return (
        "rag-eval-verification-query:"
        + sha256(
            "\x1f".join(
                (
                    verification_id,
                    dataset_role,
                    " ".join(query_text.casefold().split()),
                    expected_runtime_entry_id,
                )
            ).encode("utf-8")
        ).hexdigest()
    )


def _verification_outcome_id(verification_query_id: str) -> str:
    return (
        "rag-eval-verification-outcome:"
        + sha256(verification_query_id.encode("utf-8")).hexdigest()
    )


def _verification_query_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalVerificationQuery:
    return WorkbenchRagEvalVerificationQuery(
        verification_query_id=_text_from_row(row, "verification_query_id"),
        revision_id=_text_from_row(row, "revision_id"),
        run_id=_text_from_row(row, "run_id"),
        project_id=_text_from_row(row, "project_id"),
        query_text=_text_from_row(row, "query_text"),
        dataset_role=WorkbenchRagEvalVerificationDatasetRole(
            _text_from_row(row, "dataset_role")
        ),
        expected_runtime_entry_id=_text_from_row(row, "expected_runtime_entry_id"),
        expected_fact_id=_text_from_row(row, "expected_fact_id"),
        source_runtime_entry_id=_text_from_row(row, "source_runtime_entry_id"),
        question_id=_optional_text_from_row(row, "question_id"),
        source_outcome_id=_optional_text_from_row(row, "source_outcome_id"),
        promotion_id=_optional_text_from_row(row, "promotion_id"),
        created_at=_datetime_from_row(row, "created_at"),
    )


def _verification_outcome_pair_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalVerificationOutcomePair:
    return WorkbenchRagEvalVerificationOutcomePair(
        verification_query_id=_text_from_row(row, "verification_query_id"),
        dataset_role=WorkbenchRagEvalVerificationDatasetRole(
            _text_from_row(row, "dataset_role")
        ),
        expected_runtime_entry_id=_text_from_row(row, "expected_runtime_entry_id"),
        before_expected_rank=_optional_int_from_row(row, "before_expected_rank"),
        after_expected_rank=_optional_int_from_row(row, "after_expected_rank"),
        before_expected_score=_optional_float_from_row(row, "before_expected_score"),
        after_expected_score=_optional_float_from_row(row, "after_expected_score"),
        before_best_competitor_runtime_entry_id=_optional_text_from_row(
            row,
            "before_best_competitor_runtime_entry_id",
        ),
        after_best_competitor_runtime_entry_id=_optional_text_from_row(
            row,
            "after_best_competitor_runtime_entry_id",
        ),
        before_score_margin=_optional_float_from_row(row, "before_score_margin"),
        after_score_margin=_optional_float_from_row(row, "after_score_margin"),
        before_classification=WorkbenchRagEvalRetrievalClassification(
            _text_from_row(row, "before_classification")
        ),
        after_classification=WorkbenchRagEvalRetrievalClassification(
            _text_from_row(row, "after_classification")
        ),
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


def _promotion_application_snapshot_from_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    expected_embedding_model_id: str,
) -> WorkbenchRagEvalPromotionApplicationSnapshot:
    if not rows:
        raise ValueError("promotion application snapshot requires rows")
    first = rows[0]
    embedding_model_id = _optional_text_from_row(first, "embedding_model_id")
    if embedding_model_id is None:
        raise WorkbenchRagEvalPromotionConflictError(
            "current runtime embedding is missing",
            code=WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT,
            promotion_ids=tuple(_text_from_row(row, "promotion_id") for row in rows),
            runtime_entry_id=_text_from_row(first, "runtime_entry_id"),
        )
    if embedding_model_id != expected_embedding_model_id:
        raise WorkbenchRagEvalPromotionConflictError(
            "runtime embedding model changed",
            code=WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT,
            promotion_ids=tuple(_text_from_row(row, "promotion_id") for row in rows),
            runtime_entry_id=_text_from_row(first, "runtime_entry_id"),
        )
    dimensions = _int_from_row(first, "embedding_dimensions")
    if dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
        raise WorkbenchRagEvalPromotionConflictError(
            "runtime embedding dimensions violate canonical invariant",
            code=WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT,
            promotion_ids=tuple(_text_from_row(row, "promotion_id") for row in rows),
            runtime_entry_id=_text_from_row(first, "runtime_entry_id"),
        )
    embedding = _vector_tuple(first.get("current_embedding"))
    if len(embedding) != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
        raise WorkbenchRagEvalPromotionConflictError(
            "runtime embedding vector violates canonical dimensions",
            code=WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT,
            promotion_ids=tuple(_text_from_row(row, "promotion_id") for row in rows),
            runtime_entry_id=_text_from_row(first, "runtime_entry_id"),
        )
    candidates = tuple(
        WorkbenchRagEvalPromotionApplicationCandidate(
            promotion_id=_text_from_row(row, "promotion_id"),
            run_id=_text_from_row(row, "run_id"),
            question_id=_text_from_row(row, "question_id"),
            target_fact_id=_text_from_row(row, "target_fact_id"),
            question=_text_from_row(row, "question"),
            status=WorkbenchRagEvalPromotionStatus(_text_from_row(row, "status")),
        )
        for row in rows
    )
    possible_questions = _text_tuple(first.get("possible_questions"))
    active_promoted_questions = _normalized_unique_questions(
        _text_tuple(first.get("active_promoted_questions"))
    )
    snapshot = WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id=_text_from_row(first, "project_id"),
        runtime_entry_id=_text_from_row(first, "runtime_entry_id"),
        fact_id=_text_from_row(first, "fact_id"),
        runtime_status=_text_from_row(first, "runtime_status"),
        runtime_visibility=_text_from_row(first, "runtime_visibility"),
        claim=_text_from_row(first, "claim"),
        possible_questions=possible_questions,
        active_promoted_questions=active_promoted_questions,
        exclusion_scope=_optional_text_from_row(first, "exclusion_scope"),
        embedding_text=_text_from_row(first, "embedding_text"),
        embedding=embedding,
        embedding_model_id=embedding_model_id,
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        candidates=candidates,
        runtime_hash=stable_runtime_snapshot_hash(
            possible_questions=possible_questions,
            embedding_text=_text_from_row(first, "embedding_text"),
            embedding=embedding,
            embedding_model_id=embedding_model_id,
            embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        ),
        active_revision_id=_optional_text_from_row(
            first,
            "active_revision_id",
        ),
    )
    for row in rows[1:]:
        if _text_from_row(row, "project_id") != snapshot.project_id:
            raise RuntimeError("promotion application rows cross project boundary")
        if _text_from_row(row, "runtime_entry_id") != snapshot.runtime_entry_id:
            raise RuntimeError("promotion application rows cross runtime boundary")
        if _text_from_row(row, "fact_id") != snapshot.fact_id:
            raise RuntimeError("promotion application rows disagree on fact id")
        if _text_from_row(row, "runtime_status") != snapshot.runtime_status:
            raise RuntimeError("promotion application rows disagree on runtime status")
        if _text_from_row(row, "runtime_visibility") != snapshot.runtime_visibility:
            raise RuntimeError(
                "promotion application rows disagree on runtime visibility"
            )
        if _text_from_row(row, "embedding_text") != snapshot.embedding_text:
            raise RuntimeError("promotion application rows disagree on embedding text")
        if (
            _normalized_unique_questions(
                _text_tuple(row.get("active_promoted_questions"))
            )
            != snapshot.active_promoted_questions
        ):
            raise RuntimeError(
                "promotion application rows disagree on active promoted aliases"
            )
        if _optional_text_from_row(row, "active_revision_id") != (
            snapshot.active_revision_id
        ):
            raise RuntimeError("promotion application rows disagree on active revision")
    return snapshot


def _promotion_application_claim_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalPromotionApplicationClaim:
    return WorkbenchRagEvalPromotionApplicationClaim(
        application_key=_text_from_row(row, "application_key"),
        project_id=_text_from_row(row, "project_id"),
        runtime_entry_id=_text_from_row(row, "runtime_entry_id"),
        source_rag_eval_run_id=_text_from_row(row, "source_rag_eval_run_id"),
        promotion_ids=_text_tuple(row.get("promotion_ids")),
        previous_runtime_hash=_text_from_row(row, "previous_runtime_hash"),
        status=WorkbenchRagEvalPromotionApplicationClaimStatus(
            _text_from_row(row, "status")
        ),
        lease_owner=_text_from_row(row, "lease_owner"),
        lease_expires_at=_datetime_from_row(row, "lease_expires_at"),
        revision_id=_optional_text_from_row(row, "revision_id"),
        created_at=_datetime_from_row(row, "created_at"),
        updated_at=_datetime_from_row(row, "updated_at"),
        completed_at=_optional_datetime_from_row(row, "completed_at"),
    )


def _assert_claim_identity(
    *,
    claim: WorkbenchRagEvalPromotionApplicationClaim,
    project_id: str,
    runtime_entry_id: str,
    source_rag_eval_run_id: str,
    promotion_ids: tuple[str, ...],
    previous_runtime_hash: str,
) -> None:
    if (
        claim.project_id != project_id
        or claim.runtime_entry_id != runtime_entry_id
        or claim.source_rag_eval_run_id != source_rag_eval_run_id
        or tuple(sorted(claim.promotion_ids)) != tuple(sorted(promotion_ids))
        or claim.previous_runtime_hash != previous_runtime_hash
    ):
        raise WorkbenchRagEvalPromotionConflictError(
            "application claim identity does not match requested group",
            code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
            promotion_ids=promotion_ids,
            runtime_entry_id=runtime_entry_id,
        )


def _embedding_revision_read_model_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
    return WorkbenchRagEvalEmbeddingRevisionReadModel(
        revision_id=_text_from_row(row, "revision_id"),
        project_id=_text_from_row(row, "project_id"),
        runtime_entry_id=_text_from_row(row, "runtime_entry_id"),
        source_rag_eval_run_id=_text_from_row(
            row,
            "source_rag_eval_run_id",
        ),
        promotion_ids=_text_tuple(row.get("promotion_ids")),
        status=WorkbenchRagEvalEmbeddingRevisionStatus(_text_from_row(row, "status")),
        previous_promoted_questions=_text_tuple(row.get("previous_promoted_questions")),
        new_promoted_questions=_text_tuple(row.get("new_promoted_questions")),
        created_at=_datetime_from_row(row, "created_at"),
        accepted_at=_optional_datetime_from_row(row, "accepted_at"),
        regression_failed_at=_optional_datetime_from_row(
            row,
            "regression_failed_at",
        ),
        rolled_back_at=_optional_datetime_from_row(row, "rolled_back_at"),
        available_actions=WorkbenchRagEvalEmbeddingRevisionAvailableActions(
            can_accept=_bool_from_row_default_false(row, "can_accept"),
            can_rollback=_bool_from_row_default_false(row, "can_rollback"),
        ),
    )


def _embedding_revision_read_model(
    revision: WorkbenchRagEvalEmbeddingRevision,
) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
    return WorkbenchRagEvalEmbeddingRevisionReadModel(
        revision_id=revision.revision_id,
        project_id=revision.project_id,
        runtime_entry_id=revision.runtime_entry_id,
        source_rag_eval_run_id=revision.source_rag_eval_run_id,
        promotion_ids=tuple(sorted(revision.promotion_ids)),
        status=revision.status,
        previous_promoted_questions=revision.previous_promoted_questions,
        new_promoted_questions=revision.new_promoted_questions,
        created_at=revision.created_at,
        accepted_at=revision.accepted_at,
        regression_failed_at=revision.regression_failed_at,
        rolled_back_at=revision.rolled_back_at,
        available_actions=WorkbenchRagEvalEmbeddingRevisionAvailableActions(
            can_accept=False,
            can_rollback=(
                revision.status
                is WorkbenchRagEvalEmbeddingRevisionStatus.REGRESSION_FAILED
            ),
        ),
    )


async def _load_embedding_revision_by_id(
    connection: WorkbenchRagEvalConnectionLike,
    revision_id: str,
) -> WorkbenchRagEvalEmbeddingRevisionReadModel | None:
    row = await connection.fetchrow(
        "SELECT "
        + WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_COLUMNS_SQL
        + """
        FROM knowledge_workbench_rag_eval_embedding_revisions
        WHERE revision_id = $1
        """,
        revision_id,
    )
    return _embedding_revision_read_model_from_row(row) if row is not None else None


async def _load_embedding_revision_full_for_update(
    connection: WorkbenchRagEvalConnectionLike,
    revision_id: str,
    project_id: str,
) -> WorkbenchRagEvalEmbeddingRevision:
    row = await connection.fetchrow(
        "SELECT "
        + WORKBENCH_RAG_EVAL_EMBEDDING_REVISION_FULL_COLUMNS_SQL
        + """
        FROM knowledge_workbench_rag_eval_embedding_revisions
        WHERE revision_id = $1
          AND project_id = $2::uuid
        FOR UPDATE
        """,
        revision_id,
        project_id,
    )
    if row is None:
        raise WorkbenchRagEvalPromotionNotFoundError("Embedding revision not found")
    return _embedding_revision_full_from_row(row)


def _embedding_revision_full_from_row(
    row: Mapping[str, object],
) -> WorkbenchRagEvalEmbeddingRevision:
    return WorkbenchRagEvalEmbeddingRevision(
        revision_id=_text_from_row(row, "revision_id"),
        project_id=_text_from_row(row, "project_id"),
        runtime_entry_id=_text_from_row(row, "runtime_entry_id"),
        source_rag_eval_run_id=_text_from_row(row, "source_rag_eval_run_id"),
        promotion_ids=_text_tuple(row.get("promotion_ids")),
        status=WorkbenchRagEvalEmbeddingRevisionStatus(_text_from_row(row, "status")),
        previous_embedding_text=_text_from_row(row, "previous_embedding_text"),
        new_embedding_text=_text_from_row(row, "new_embedding_text"),
        previous_embedding=_vector_tuple(row.get("previous_embedding")),
        new_embedding=_vector_tuple(row.get("new_embedding")),
        previous_promoted_questions=_text_tuple(row.get("previous_promoted_questions")),
        new_promoted_questions=_text_tuple(row.get("new_promoted_questions")),
        embedding_model_id=_text_from_row(row, "embedding_model_id"),
        embedding_dimensions=_int_from_row(row, "embedding_dimensions"),
        previous_runtime_hash=_text_from_row(row, "previous_runtime_hash"),
        new_runtime_hash=_text_from_row(row, "new_runtime_hash"),
        created_at=_datetime_from_row(row, "created_at"),
        accepted_at=_optional_datetime_from_row(row, "accepted_at"),
        regression_failed_at=_optional_datetime_from_row(
            row,
            "regression_failed_at",
        ),
        rolled_back_at=_optional_datetime_from_row(row, "rolled_back_at"),
    )


def _assert_revision_matches_snapshot(
    *,
    snapshot: WorkbenchRagEvalPromotionApplicationSnapshot,
    revision: WorkbenchRagEvalEmbeddingRevision,
) -> None:
    expected_ids = tuple(
        sorted(candidate.promotion_id for candidate in snapshot.candidates)
    )
    if tuple(sorted(revision.promotion_ids)) != expected_ids:
        raise ValueError("revision promotion_ids do not match snapshot candidates")
    if revision.project_id != snapshot.project_id:
        raise ValueError("revision project_id does not match snapshot")
    if revision.runtime_entry_id != snapshot.runtime_entry_id:
        raise ValueError("revision runtime_entry_id does not match snapshot")
    if revision.source_rag_eval_run_id != snapshot.source_rag_eval_run_id:
        raise ValueError("revision source run does not match snapshot")
    if (
        revision.status
        is not WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
    ):
        raise ValueError("application revision must be PENDING_VERIFICATION")
    if revision.previous_embedding_text != snapshot.embedding_text:
        raise ValueError("revision previous embedding text does not match snapshot")
    if revision.previous_embedding != snapshot.embedding:
        raise ValueError("revision previous embedding does not match snapshot")
    if revision.previous_promoted_questions != snapshot.possible_questions:
        raise ValueError("revision previous aliases do not match snapshot")
    if revision.embedding_model_id != snapshot.embedding_model_id:
        raise ValueError("revision embedding model does not match snapshot")
    if (
        revision.embedding_dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
        or snapshot.embedding_dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
    ):
        raise ValueError("revision embedding dimensions violate canonical invariant")
    if revision.previous_runtime_hash != snapshot.runtime_hash:
        raise ValueError("revision previous runtime hash does not match snapshot")
    expected_new_hash = stable_runtime_snapshot_hash(
        possible_questions=revision.new_promoted_questions,
        embedding_text=revision.new_embedding_text,
        embedding=revision.new_embedding,
        embedding_model_id=revision.embedding_model_id,
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    )
    if revision.new_runtime_hash != expected_new_hash:
        raise ValueError("revision new runtime hash is invalid")


def _assert_locked_candidates_match(
    *,
    expected: WorkbenchRagEvalPromotionApplicationSnapshot,
    locked: WorkbenchRagEvalPromotionApplicationSnapshot,
) -> None:
    def identity(
        snapshot: WorkbenchRagEvalPromotionApplicationSnapshot,
    ) -> tuple[tuple[str, str, str, str, str], ...]:
        return tuple(
            sorted(
                (
                    candidate.promotion_id,
                    candidate.run_id,
                    candidate.question_id,
                    candidate.target_fact_id,
                    candidate.question,
                )
                for candidate in snapshot.candidates
            )
        )

    if identity(expected) != identity(locked):
        raise WorkbenchRagEvalPromotionConflictError(
            "promotion rows changed after immutable snapshot",
            code=WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT,
            promotion_ids=tuple(
                candidate.promotion_id for candidate in expected.candidates
            ),
            runtime_entry_id=expected.runtime_entry_id,
        )
    if expected.active_promoted_questions != locked.active_promoted_questions:
        raise WorkbenchRagEvalPromotionConflictError(
            "active promoted aliases changed after immutable snapshot",
            code=WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT,
            promotion_ids=tuple(
                candidate.promotion_id for candidate in expected.candidates
            ),
            runtime_entry_id=expected.runtime_entry_id,
        )


def _normalized_unique_questions(values: tuple[str, ...]) -> tuple[str, ...]:
    by_normalized: dict[str, str] = {}
    for value in values:
        normalized = normalize_workbench_rag_eval_question(value)
        if not normalized:
            raise ValueError("promoted alias normalizes to empty")
        by_normalized.setdefault(normalized, value.strip())
    return tuple(by_normalized[key] for key in sorted(by_normalized))


def _require_affected_rows(
    result: object,
    *,
    expected: int,
    operation: str,
) -> None:
    if not isinstance(result, str):
        raise RuntimeError(f"{operation} did not return an asyncpg command tag")
    try:
        affected = int(result.rsplit(" ", 1)[1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"{operation} returned invalid command tag") from exc
    if affected != expected:
        raise WorkbenchRagEvalPromotionConflictError(
            f"{operation} affected {affected} rows; expected {expected}",
            code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
        )


async def _append_promotion_revision_event(
    connection: WorkbenchRagEvalConnectionLike,
    *,
    event_type: str,
    message: str,
    payload: Mapping[str, object],
    revision: WorkbenchRagEvalEmbeddingRevision,
) -> None:
    event_id = (
        f"workflow-event:{revision.source_rag_eval_run_id}:"
        f"{event_type}:{revision.revision_id}"
    )
    payload_json = json.dumps(
        dict(payload),
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    row = await connection.fetchrow(
        """
        INSERT INTO workflow_runtime_outbox_events (
            event_id,
            event_type,
            workflow_run_id,
            payload,
            occurred_at,
            causation_command_id,
            correlation_id
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, NULL, $6)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING sequence_number
        """,
        event_id,
        event_type,
        revision.source_rag_eval_run_id,
        payload_json,
        revision.created_at,
        revision.revision_id,
    )
    timeline_id = (
        f"timeline:{revision.source_rag_eval_run_id}:"
        f"{event_type}:{revision.revision_id}"
    )
    await connection.execute(
        """
        INSERT INTO workflow_runtime_timeline_entries (
            timeline_entry_id,
            workflow_run_id,
            event_type,
            phase,
            severity,
            message,
            payload_summary,
            occurred_at,
            source_ref,
            work_item_id,
            attempt_id
        )
        VALUES (
            $1, $2, $3, 'POST_PROMOTION_VERIFICATION',
            'info', $4, $5::jsonb, $6, $7, NULL, NULL
        )
        ON CONFLICT (timeline_entry_id) DO NOTHING
        """,
        timeline_id,
        revision.source_rag_eval_run_id,
        event_type,
        message,
        payload_json,
        revision.created_at,
        revision.runtime_entry_id,
    )
    if row is not None:
        sequence_number = row.get("sequence_number")
        if not isinstance(sequence_number, int):
            raise TypeError("outbox sequence_number must be int")
        notification_payload = json.dumps(
            {
                "sequence_number": sequence_number,
                "event_id": event_id,
                "event_type": event_type,
                "workflow_run_id": revision.source_rag_eval_run_id,
                "occurred_at": revision.created_at.isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        await connection.execute(
            "SELECT pg_notify($1, $2)",
            "workflow_live_state_changed",
            notification_payload,
        )


def _vector_tuple(value: object) -> tuple[float, ...]:
    decoded: object = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise TypeError("embedding vector text must be JSON-compatible") from exc
    if not isinstance(decoded, Sequence) or isinstance(
        decoded,
        (str, bytes, bytearray),
    ):
        raise TypeError("embedding vector must be a sequence")
    result: list[float] = []
    for item in decoded:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError("embedding vector values must be numeric")
        result.append(float(item))
    return tuple(result)


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
        outcome_id=_text_from_row(row, "outcome_id"),
        adjudication_id=_text_from_row(row, "adjudication_id"),
        target_runtime_entry_id=_text_from_row(
            row,
            "target_runtime_entry_id",
        ),
        target_fact_id=_text_from_row(row, "target_fact_id"),
        question=_text_from_row(row, "question"),
        status=WorkbenchRagEvalPromotionStatus(_text_from_row(row, "status")),
        reason=_optional_text_from_row(row, "reason"),
        expected_rank=_optional_int_from_row(row, "expected_rank"),
        expected_score=_optional_float_from_row(row, "expected_score"),
        competitor_runtime_entry_id=_optional_text_from_row(
            row,
            "competitor_runtime_entry_id",
        ),
        competitor_fact_id=_optional_text_from_row(
            row,
            "competitor_fact_id",
        ),
        competitor_score=_optional_float_from_row(
            row,
            "competitor_score",
        ),
        score_margin=_optional_float_from_row(row, "score_margin"),
        created_at=_datetime_from_row(row, "created_at"),
        reviewed_at=_optional_datetime_from_row(row, "reviewed_at"),
        review_reason=_optional_text_from_row(row, "review_reason"),
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


def _json_object_from_row(row: Mapping[str, object], key: str) -> JsonObject | None:
    value = row.get(key)
    if value is None:
        return None
    return json_object_from_unknown(value)


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


def _bool_from_row_default_false(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key, False)
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
