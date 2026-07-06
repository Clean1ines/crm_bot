from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_CANDIDATES_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_FOR_UPDATE_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL,
    WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_UPDATE_SQL,
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

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        self.fetch_calls.append((query, args))
        return self.rows

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_result

    async def execute(self, query: str, *args: object) -> object:
        self.execute_calls.append((query, args))
        return "UPDATE 1"

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
        "status": "candidate",
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
        "promotion_candidate_count": 2,
    }


def test_repository_reads_published_workbench_runtime_entries_not_legacy_tables() -> (
    None
):
    sql = PUBLISHED_ENTRIES_FOR_WORKBENCH_RAG_EVAL_SQL

    assert "knowledge_workbench_runtime_retrieval_entries" in sql
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in sql
    assert "knowledge_workbench_canonical_facts" not in sql
    assert "JOIN knowledge_workbench_canonical_facts" not in sql
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
async def test_get_run_summary_sql_casts_project_id_and_does_not_select_run_star() -> None:
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


@pytest.mark.asyncio
async def test_get_latest_run_summary_sql_casts_project_id_and_does_not_select_run_star() -> None:
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


def test_promotion_application_target_sql_reads_runtime_entries_only() -> None:
    target_sqls = (
        WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_SQL,
        WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGET_FOR_UPDATE_SQL,
        WORKBENCH_RAG_EVAL_PROMOTION_APPLICATION_TARGETS_FOR_UPDATE_SQL,
    )

    for sql in target_sqls:
        assert "knowledge_workbench_rag_eval_promoted_questions" in sql
        assert "knowledge_workbench_runtime_retrieval_entries" in sql
        assert "knowledge_workbench_canonical_facts" not in sql
        assert "JOIN knowledge_workbench_canonical_facts" not in sql
        assert "fact.status" not in sql
        assert "fact.fact_id" not in sql
        assert "entry.visibility = 'published'" in sql
        assert "entry.status = 'active'" in sql
        assert "entry.possible_questions AS runtime_possible_questions" in sql
        assert "entry.possible_questions AS fact_possible_questions" in sql
        assert "entry.exclusion_scope" in sql
        assert "entry.evidence_block" in sql
        assert "entry.triples" in sql
        assert "entry.embedding_text AS existing_embedding_text" in sql
        assert "FOR UPDATE OF promotion, entry, fact" not in sql


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
                "prompt_version": "prompt-v1",
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
                "prompt_version": "prompt-v1",
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
                "target_runtime_entry_id": "entry-1",
                "target_fact_id": "fact-1",
                "question": "Плохой retrieval вопрос?",
                "status": "candidate",
                "created_at": _now(),
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
    assert candidates[0].applied_at is None


@pytest.mark.asyncio
async def test_apply_promotion_candidate_updates_runtime_entry_and_embedding_only() -> None:
    connection = FakeConnection(fetchrow_result=_promotion_target_row())

    result = await PostgresWorkbenchRagEvalRepository(
        connection
    ).apply_promotion_candidate(
        project_id="11111111-1111-1111-1111-111111111111",
        promotion_id="promotion-1",
        embedding_model_id="text-embedding-3-small",
        dimensions=2,
        embedding=(0.1, 0.2),
        embedding_text="Claim:\nRuntime claim\n\nPossible questions:\nOld question?\nHow ask?",
        embedding_text_hash="hash-1",
        applied_at=_now(),
    )

    executed_sql = "\n".join(query for query, _ in connection.execute_calls)
    assert result.status.value == "applied"
    assert result.possible_question_count == 2
    assert "UPDATE knowledge_workbench_canonical_facts" not in executed_sql
    assert "UPDATE knowledge_workbench_runtime_retrieval_entries" in executed_sql
    assert "possible_questions = $3::jsonb" in executed_sql
    assert "embedding_text = $4" in executed_sql
    assert "visibility = 'published'" in executed_sql
    assert "status = 'active'" in executed_sql
    assert (
        "DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings"
        in executed_sql
    )
    assert (
        "INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings"
        in executed_sql
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
