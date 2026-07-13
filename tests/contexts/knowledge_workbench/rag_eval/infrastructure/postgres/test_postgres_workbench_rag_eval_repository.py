from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRetrievalOutcome,
)

from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_FOR_UPDATE_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_RUN_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL,
    WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL,
    PostgresWorkbenchRagEvalRepository,
)


@dataclass(slots=True)
class FakeTransaction:
    async def __aenter__(self) -> object:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None:
        return None


@dataclass(slots=True)
class FakeConnection:
    fetch_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    rows: list[Mapping[str, object]] = field(default_factory=list)
    fetchrow_result: Mapping[str, object] | None = None
    execute_result: str = "UPDATE 1"

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        self.fetch_calls.append((query, args))
        return self.rows

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_result

    async def execute(self, query: str, *args: object) -> object:
        self.execute_calls.append((query, args))
        return self.execute_result

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _promotion_target_row() -> Mapping[str, object]:
    return {
        "promotion_id": "promotion-1",
        "run_id": "run-1",
        "question_id": "question-1",
        "project_id": "11111111-1111-1111-1111-111111111111",
        "target_runtime_entry_id": "runtime-entry-1",
        "target_fact_id": "legacy-fact-1",
        "question": "Как спросить иначе?",
        "status": "approved",
        "created_at": _now(),
        "applied_at": None,
        "claim": "Runtime claim",
        "runtime_possible_questions": ["Old question?"],
        "fact_possible_questions": ["Old question?"],
        "exclusion_scope": "Not for internal-only policies",
        "existing_embedding_text": "Claim:\nRuntime claim",
    }


def _summary_row() -> Mapping[str, object]:
    return {
        "run_id": "run-1",
        "project_id": "11111111-1111-1111-1111-111111111111",
        "publication_id": "publication-1",
        "source_document_ref": "source-document-1",
        "status": "completed",
        "current_phase": "completed",
        "question_generation_model": "model-1",
        "question_generation_prompt_version": "prompt-v1",
        "total_entries": 2,
        "total_questions": 4,
        "completed_questions": 4,
        "top1_hits": 1,
        "top3_hits": 3,
        "top5_hits": 4,
        "misses": 0,
        "created_at": _now(),
        "started_at": _now(),
        "completed_at": _now(),
        "error_message": None,
        "blocked_reason": None,
        "failed_reason": None,
        "updated_at": _now(),
        "selected_entries": 2,
        "scheduled_generation_items": 2,
        "waiting_work_items": 0,
        "running_work_items": 0,
        "completed_work_items": 2,
        "failed_work_items": 0,
        "generated_question_sets": 2,
        "capacity_next_due_at": None,
        "capacity_model_ref": None,
        "capacity_account_ref": None,
        "adjudication_total": 2,
        "adjudication_waiting": 0,
        "adjudication_running": 0,
        "adjudication_completed": 2,
        "adjudication_failed": 0,
        "persisted_promotion_candidate_count": 2,
        "computed_promotion_candidate_count": 2,
    }


def test_repository_reads_published_workbench_runtime_entries_not_legacy_tables() -> (
    None
):
    sql = PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL

    assert "knowledge_workbench_runtime_retrieval_entries" in sql
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in sql
    assert "knowledge_workbench_" + "canonical_facts" not in sql
    assert "JOIN knowledge_workbench_" + "canonical_facts" not in sql
    assert "fact.status" not in sql
    assert "fact.fact_id" not in sql
    assert "knowledge_" + "retrieval_" + "surface" not in sql
    assert "knowledge_workbench_surfaces" not in sql
    assert "answer_text" not in sql
    assert "entry.visibility = 'published'" in sql
    assert "entry.status = 'active'" in sql
    assert "entry.exclusion_scope" in sql
    assert "entry.evidence_block" in sql
    assert "entry.triples" in sql
    assert "entry.source_claim_refs" in sql
    assert "entry.source_document_ref" in sql
    assert "entry.curation_item_ref" in sql
    assert "emb.runtime_entry_id = entry.runtime_entry_id" in sql


@pytest.mark.asyncio
async def test_transition_run_progress_updates_state_and_progress_atomically() -> None:
    connection = FakeConnection()
    progress = WorkbenchRagEvalRunProgress(
        selected_entries=4,
        scheduled_generation_items=4,
        waiting=2,
        running=1,
        completed=1,
        generated_question_sets=1,
    )

    await PostgresWorkbenchRagEvalRepository(connection).transition_run_progress(
        run_id="run-1",
        project_id="11111111-1111-1111-1111-111111111111",
        status=WorkbenchRagEvalRunStatus.WAITING_CAPACITY,
        current_phase=WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
        progress=progress,
        updated_at=_now(),
        capacity_next_due_at=_now(),
        capacity_model_ref="qwen/qwen3-32b",
        capacity_account_ref="groq_org_primary",
    )

    assert len(connection.execute_calls) == 1
    sql, args = connection.execute_calls[0]
    assert "SET status = $3" in sql
    assert "current_phase = $4" in sql
    assert "scheduled_generation_items = $9" in sql
    assert args[2:4] == ("waiting_capacity", "question_generation")
    assert args[8:14] == (4, 2, 1, 1, 0, 1)


@pytest.mark.asyncio
async def test_get_run_summary_sql_casts_project_id_and_does_not_select_run_star() -> (
    None
):
    connection = FakeConnection(fetchrow_result=_summary_row())

    summary = await PostgresWorkbenchRagEvalRepository(connection).get_run(
        run_id="run-1",
        project_id="11111111-1111-1111-1111-111111111111",
    )

    sql = connection.fetchrow_calls[0][0]
    assert "run.project_id::text AS project_id" in sql
    assert "run.*" not in sql
    assert "WHERE run.run_id = $1" in sql
    assert "AND run.project_id = $2::uuid" in sql
    assert summary is not None
    assert summary.project_id == "11111111-1111-1111-1111-111111111111"
    assert summary.promotion_candidate_count == 2
    assert summary.current_phase.value == "completed"
    assert summary.progress.scheduled_generation_items == 2


@pytest.mark.asyncio
async def test_get_latest_run_summary_sql_casts_project_id_and_does_not_select_run_star() -> (
    None
):
    connection = FakeConnection(fetchrow_result=_summary_row())

    summary = await PostgresWorkbenchRagEvalRepository(connection).get_latest_run(
        project_id="11111111-1111-1111-1111-111111111111",
    )

    sql = connection.fetchrow_calls[0][0]
    assert "run.project_id::text AS project_id" in sql
    assert "run.*" not in sql
    assert "WHERE run.project_id = $1::uuid" in sql
    assert "ORDER BY run.created_at DESC" in sql
    assert summary is not None
    assert summary.project_id == "11111111-1111-1111-1111-111111111111"
    assert summary.promotion_candidate_count == 2
    assert "run.current_phase" in sql
    assert summary.updated_at == _now()


def test_details_sql_reads_questions_results_and_candidates_without_legacy_tables() -> (
    None
):
    combined = (
        WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL
        + WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL
    )
    assert "knowledge_workbench_rag_eval_questions" in combined
    assert "knowledge_workbench_rag_eval_retrieval_results" in combined
    assert "knowledge_workbench_rag_eval_promoted_questions" in combined


@pytest.mark.asyncio
async def test_repository_persists_roles_and_canonical_outcome() -> None:
    connection = FakeConnection()
    repository = PostgresWorkbenchRagEvalRepository(connection)
    await repository.save_question_roles(
        roles={"question-1": WorkbenchRagEvalQuestionRole.HOLDOUT}
    )
    outcome = WorkbenchRagEvalRetrievalOutcome(
        outcome_id="outcome-1",
        run_id="run-1",
        question_id="question-1",
        project_id="11111111-1111-1111-1111-111111111111",
        evaluation_stage="initial",
        expected_runtime_entry_id="entry-1",
        expected_fact_id="fact-1",
        expected_rank=2,
        expected_score=0.8,
        best_competitor_runtime_entry_id="entry-2",
        best_competitor_fact_id="fact-2",
        best_competitor_score=0.5,
        score_margin=0.3,
        classification=(WorkbenchRagEvalRetrievalClassification.PASS_WEAK),
        created_at=_now(),
    )
    assert await repository.save_retrieval_outcomes(outcomes=(outcome,)) == (outcome,)
    assert "promotion_eligible = CASE" in connection.execute_calls[0][0]
    assert (
        "knowledge_workbench_rag_eval_retrieval_outcomes"
        in connection.execute_calls[1][0]
    )


def test_role_and_outcome_migrations_enforce_canonical_contract() -> None:
    root = Path(__file__).parents[6]
    roles = (
        root / "migrations/121_add_workbench_rag_eval_question_roles.sql"
    ).read_text()
    outcomes = (
        root / "migrations/122_create_workbench_rag_eval_retrieval_outcomes.sql"
    ).read_text()
    assert "holdout_not_promotion_eligible" in roles
    assert "existing_alias_retrieval_failure" in outcomes
    assert "score_margin" in outcomes


@pytest.mark.asyncio
async def test_repository_materializes_idempotent_baseline_from_persisted_schedules() -> (
    None
):
    combined = (
        WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL
        + WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL
    )
    connection = FakeConnection(
        rows=[
            {
                "run_id": "run-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "runtime_entry_id": "runtime-entry-1",
                "expected_fact_id": "fact-1",
                "question": "Как оплатить?",
            },
            {
                "run_id": "run-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "runtime_entry_id": "runtime-entry-1",
                "expected_fact_id": "fact-1",
                "question": "  как   оплатить ? ",
            },
            {
                "run_id": "run-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "runtime_entry_id": "runtime-entry-1",
                "expected_fact_id": "fact-1",
                "question": "как оплатить!",
            },
        ],
        execute_result="INSERT 0 1",
    )
    count = await PostgresWorkbenchRagEvalRepository(
        connection
    ).materialize_baseline_questions(
        run_id="run-1",
        project_id="11111111-1111-1111-1111-111111111111",
        created_at=_now(),
    )
    sql, _ = connection.fetch_calls[0]
    assert count == 1
    assert "execution_work_item_schedules" in sql
    assert "workbench_rag_eval.question_generation" in sql
    assert "md5" not in sql
    assert "possible.question)" not in sql
    insert_sql = connection.execute_calls[0][0]
    assert "ON CONFLICT (question_id) DO NOTHING" in insert_sql
    insert_args = connection.execute_calls[0][1]
    assert insert_args[0].startswith("rag-eval-baseline:")
    assert insert_args[7] == "published_possible_question"
    assert insert_args[18] == "baseline"
    assert (
        "question.project_id = $1::uuid"
        in WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL
    )
    assert "question.run_id = $2" in WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL
    assert "project_id = $1::uuid" in WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL
    assert "run_id = $2" in WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL
    assert "answer_text" not in combined
    assert "knowledge_" + "retrieval_" + "surface" not in combined
    assert "knowledge_workbench_surfaces" not in combined


@pytest.mark.asyncio
async def test_mark_questions_evaluated_persists_evaluated_at_timestamp() -> None:
    connection = FakeConnection()

    await PostgresWorkbenchRagEvalRepository(connection).mark_questions_evaluated(
        run_id="run-1",
        question_ids=("question-1", "question-2"),
        evaluated_at=_now(),
    )

    sql, args = connection.execute_calls[0]
    assert "evaluated_at = $3" in sql
    assert args == ("run-1", ["question-1", "question-2"], _now())


def test_promotion_application_sql_uses_revision_aware_runtime_boundary() -> None:
    target_sql = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL
    group_sql = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL
    locked_group_sql = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_FOR_UPDATE_SQL

    assert "knowledge_workbench_rag_eval_promoted_questions" in target_sql
    assert "knowledge_workbench_runtime_retrieval_entries" in target_sql
    assert "knowledge_workbench_" + "canonical_facts" not in target_sql
    assert "entry.visibility = 'published'" not in target_sql
    assert "entry.status = 'active'" not in target_sql
    assert "entry.possible_questions AS runtime_possible_questions" in target_sql

    assert "knowledge_workbench_rag_eval_embedding_revisions" in group_sql
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in group_sql
    assert "active.revision_id AS active_revision_id" in group_sql
    assert "emb.embedding::text AS current_embedding" in group_sql
    assert "FOR UPDATE OF promotion, entry" in locked_group_sql
    assert (
        "promotion.status IN ('approved', 'applied')"
        in WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_RUN_SQL
    )


@pytest.mark.asyncio
async def test_list_published_entries_for_eval_maps_runtime_entry_fields() -> None:
    connection = FakeConnection(
        rows=[
            {
                "runtime_entry_id": "runtime-entry-1",
                "publication_id": "publication-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "source_document_ref": "source-document-1",
                "fact_id": "runtime-entry-1",
                "curation_item_ref": "curation-item-1",
                "claim": "Runtime claim",
                "possible_questions": ["Question one?", "Question two?"],
                "exclusion_scope": "Not for internal-only policies",
                "evidence_block": "Runtime evidence",
                "triples": [{"subject": "A", "predicate": "is", "object": "B"}],
                "source_refs": {
                    "workflow_run_id": "workflow-1",
                    "source_document_ref": "source-document-1",
                    "curation_item_ref": "curation-item-1",
                    "source_claim_refs": ["claim-1"],
                },
                "source_claim_refs": ["claim-1"],
                "embedding_text": "Claim:\nRuntime claim",
                "score": 1.0,
                "rank": 1,
            }
        ]
    )

    entries = await PostgresWorkbenchRagEvalRepository(
        connection
    ).list_published_entries_for_eval(
        project_id="11111111-1111-1111-1111-111111111111",
        publication_id=None,
        source_document_ref=None,
        limit=10,
    )

    assert connection.fetch_calls[0][0] == PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL
    assert entries[0].runtime_entry_id == "runtime-entry-1"
    assert entries[0].fact_id == "runtime-entry-1"
    assert entries[0].claim == "Runtime claim"
    assert entries[0].possible_questions == ("Question one?", "Question two?")
    assert entries[0].exclusion_scope == "Not for internal-only policies"
    assert entries[0].evidence_block == "Runtime evidence"
    assert entries[0].source_claim_refs == ("claim-1",)
    assert entries[0].source_ref.source_document_ref == "source-document-1"
    assert entries[0].source_ref.curation_item_ref == "curation-item-1"


@pytest.mark.asyncio
async def test_list_run_questions_maps_questions_with_retrieval_results() -> None:
    connection = FakeConnection(
        rows=[
            {
                "question_id": "question-1",
                "run_id": "run-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "expected_runtime_entry_id": "expected-entry",
                "expected_fact_id": "expected-fact",
                "question": "Как спросить?",
                "question_kind": "paraphrase",
                "source": "generated",
                "generation_model": "model-1",
                "prompt_version": "workbench_rag_eval_question_variants.ru.v2",
                "contract_version": "workbench_rag_eval_questions.v2",
                "promotion_eligible": True,
                "ambiguity_risk": "low",
                "generation_rationale": "Однозначный retrieval alias",
                "generation_account_ref": "groq_org_primary",
                "generation_slot_index": 0,
                "evaluation_role": "promotion_pool",
                "status": "created",
                "created_at": _now(),
                "result_id": "result-1",
                "matched_runtime_entry_id": "expected-entry",
                "matched_fact_id": "expected-fact",
                "rank": 1,
                "score": 0.91,
                "top1_hit": True,
                "top3_hit": True,
                "top5_hit": True,
                "result_created_at": _now(),
            },
            {
                "question_id": "question-1",
                "run_id": "run-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "expected_runtime_entry_id": "expected-entry",
                "expected_fact_id": "expected-fact",
                "question": "Как спросить?",
                "question_kind": "paraphrase",
                "source": "generated",
                "generation_model": "model-1",
                "prompt_version": "workbench_rag_eval_question_variants.ru.v2",
                "contract_version": "workbench_rag_eval_questions.v2",
                "promotion_eligible": True,
                "ambiguity_risk": "low",
                "generation_rationale": "Однозначный retrieval alias",
                "generation_account_ref": "groq_org_primary",
                "generation_slot_index": 0,
                "evaluation_role": "promotion_pool",
                "status": "created",
                "created_at": _now(),
                "result_id": "result-2",
                "matched_runtime_entry_id": "other-entry",
                "matched_fact_id": "other-fact",
                "rank": 2,
                "score": 0.72,
                "top1_hit": True,
                "top3_hit": True,
                "top5_hit": True,
                "result_created_at": _now(),
            },
        ]
    )

    questions = await PostgresWorkbenchRagEvalRepository(connection).list_run_questions(
        project_id="11111111-1111-1111-1111-111111111111",
        run_id="run-1",
    )

    assert connection.fetch_calls[0][0] == WORKBENCH_RAG_EVAL_QUESTIONS_WITH_RESULTS_SQL
    assert questions[0].question_id == "question-1"
    assert questions[0].contract_version == "workbench_rag_eval_questions.v2"
    assert questions[0].promotion_eligible is True
    assert questions[0].ambiguity_risk.value == "low"
    assert questions[0].generation_rationale == "Однозначный retrieval alias"
    assert questions[0].generation_account_ref == "groq_org_primary"
    assert questions[0].generation_slot_index == 0
    assert questions[0].results[0].matched_runtime_entry_id == "expected-entry"
    assert questions[0].results[1].rank == 2
    assert "answer_text" not in str(questions[0].to_json_dict())


@pytest.mark.asyncio
async def test_list_run_promotion_candidates_maps_candidates() -> None:
    connection = FakeConnection(
        rows=[
            {
                "promotion_id": "promotion-1",
                "run_id": "run-1",
                "question_id": "question-1",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "outcome_id": "outcome-1",
                "adjudication_id": "adjudication-1",
                "target_runtime_entry_id": "entry-1",
                "target_fact_id": "fact-1",
                "question": "Плохой retrieval вопрос?",
                "status": "candidate",
                "reason": "Valid target query with weak retrieval",
                "expected_rank": 3,
                "expected_score": 0.61,
                "competitor_runtime_entry_id": "entry-2",
                "competitor_fact_id": "fact-2",
                "competitor_score": 0.73,
                "score_margin": -0.12,
                "created_at": _now(),
                "reviewed_at": None,
                "review_reason": None,
                "applied_at": None,
            }
        ]
    )

    candidates = await PostgresWorkbenchRagEvalRepository(
        connection
    ).list_run_promotion_candidates(
        project_id="11111111-1111-1111-1111-111111111111",
        run_id="run-1",
    )

    assert connection.fetch_calls[0][0] == WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL
    assert candidates[0].promotion_id == "promotion-1"
    assert candidates[0].status.value == "candidate"
    assert candidates[0].outcome_id == "outcome-1"
    assert candidates[0].adjudication_id == "adjudication-1"
    assert candidates[0].reason == "Valid target query with weak retrieval"
    assert candidates[0].expected_rank == 3
    assert candidates[0].expected_score == 0.61
    assert candidates[0].competitor_runtime_entry_id == "entry-2"
    assert candidates[0].competitor_fact_id == "fact-2"
    assert candidates[0].competitor_score == 0.73
    assert candidates[0].score_margin == -0.12
    assert candidates[0].reviewed_at is None
    assert candidates[0].review_reason is None
    assert candidates[0].applied_at is None


@pytest.mark.asyncio
async def test_review_candidate_lock_is_scoped_by_promotion_run_and_project() -> None:
    connection = FakeConnection(fetchrow_result=None)

    with pytest.raises(Exception):
        await PostgresWorkbenchRagEvalRepository(
            connection
        ).approve_promotion_candidate(
            promotion_id="promotion-1",
            run_id="run-1",
            project_id="11111111-1111-1111-1111-111111111111",
            reviewed_at=_now(),
        )

    sql, args = connection.fetchrow_calls[0]
    assert "WHERE promotion_id = $1" in sql
    assert "AND run_id = $2" in sql
    assert "AND project_id = $3::uuid" in sql
    assert args == (
        "promotion-1",
        "run-1",
        "11111111-1111-1111-1111-111111111111",
    )


def test_repository_source_does_not_use_legacy_rag_eval_or_answer_text() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "postgres_workbench_rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "answer_text",
        "knowledge_" + "retrieval_" + "surface",
        "knowledge_workbench_surfaces",
        "src." + "application." + "rag_eval",
        "Rag" + "EvalRunner",
    )
    for marker in forbidden:
        assert marker not in source


def test_active_promoted_alias_query_counts_only_applied_lifecycle_rows() -> None:
    from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
        WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL,
    )

    alias_lateral_start = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL.index(
        "LEFT JOIN LATERAL (\n    SELECT COALESCE("
    )
    alias_lateral_end = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL.index(
        ") AS applied_aliases ON TRUE",
        alias_lateral_start,
    )
    alias_lateral = WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_GROUP_SQL[
        alias_lateral_start:alias_lateral_end
    ]

    assert "applied.status = 'applied'" in alias_lateral
    for non_active_status in (
        "'rejected'",
        "'regression_failed'",
        "'rolled_back'",
    ):
        assert non_active_status not in alias_lateral
