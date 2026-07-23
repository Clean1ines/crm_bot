from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_MODEL_REF,
    WorkbenchRagEvalQuestionGenerator,
)


def _now() -> datetime:
    return datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)


def test_question_generator_exposes_explicit_generation_model() -> None:
    generator = WorkbenchRagEvalQuestionGenerator.from_prompt_file()

    assert (
        generator.generation_model
        == WORKBENCH_RAG_EVAL_QUESTION_GENERATION_MODEL_REF
        == "qwen/qwen3.6-27b"
    )


def test_persisted_question_accepts_complete_v2_metadata() -> None:
    question = WorkbenchRagEvalQuestion(
        question_id="question-1",
        run_id="run-1",
        project_id="project-1",
        expected_runtime_entry_id="entry-1",
        expected_fact_id="fact-1",
        question="Как оформить заказ?",
        question_kind=WorkbenchRagEvalQuestionKind.ACTION_FIRST,
        source=WorkbenchRagEvalQuestionSource.GENERATED,
        generation_model="qwen/qwen3.6-27b",
        prompt_version="workbench_rag_eval_question_variants.ru.v2",
        contract_version="workbench_rag_eval_questions.v2",
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        generation_rationale="Однозначный action-first retrieval alias",
        generation_account_ref="groq_org_primary",
        generation_slot_index=0,
        status=WorkbenchRagEvalQuestionStatus.CREATED,
        created_at=_now(),
        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
    )

    assert question.contract_version == "workbench_rag_eval_questions.v2"
    assert question.promotion_eligible is True
    assert question.ambiguity_risk is WorkbenchRagEvalQuestionAmbiguityRisk.LOW


@pytest.mark.parametrize(
    "risk",
    (
        WorkbenchRagEvalQuestionAmbiguityRisk.MEDIUM,
        WorkbenchRagEvalQuestionAmbiguityRisk.HIGH,
        None,
    ),
)
def test_persisted_question_rejects_non_low_risk_promotion(
    risk: WorkbenchRagEvalQuestionAmbiguityRisk | None,
) -> None:
    with pytest.raises(
        ValueError,
        match="promotion_eligible requires ambiguity_risk=low",
    ):
        WorkbenchRagEvalQuestion(
            question_id="question-1",
            run_id="run-1",
            project_id="project-1",
            expected_runtime_entry_id="entry-1",
            expected_fact_id="fact-1",
            question="Как оформить заказ?",
            question_kind=WorkbenchRagEvalQuestionKind.ACTION_FIRST,
            source=WorkbenchRagEvalQuestionSource.GENERATED,
            generation_model="qwen/qwen3.6-27b",
            prompt_version="workbench_rag_eval_question_variants.ru.v2",
            contract_version="workbench_rag_eval_questions.v2",
            promotion_eligible=True,
            ambiguity_risk=risk,
            generation_rationale="Alias",
            generation_account_ref="groq_org_primary",
            generation_slot_index=0,
            status=WorkbenchRagEvalQuestionStatus.CREATED,
            created_at=_now(),
            evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        )


def test_baseline_question_requires_canonical_source_kind_role_contract() -> None:
    question = WorkbenchRagEvalQuestion(
        question_id="baseline-1",
        run_id="run-1",
        project_id="project-1",
        expected_runtime_entry_id="entry-1",
        expected_fact_id="fact-1",
        question="Как оплатить?",
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
        created_at=_now(),
        evaluation_role=WorkbenchRagEvalQuestionRole.BASELINE,
    )

    assert question.evaluation_role is WorkbenchRagEvalQuestionRole.BASELINE


def test_baseline_question_rejects_generation_metadata_or_promotion_role() -> None:
    with pytest.raises(ValueError, match="baseline role"):
        WorkbenchRagEvalQuestion(
            question_id="baseline-1",
            run_id="run-1",
            project_id="project-1",
            expected_runtime_entry_id="entry-1",
            expected_fact_id="fact-1",
            question="Как оплатить?",
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
            created_at=_now(),
            evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        )


def test_generated_question_rejects_baseline_role() -> None:
    with pytest.raises(ValueError, match="generated question cannot have baseline"):
        WorkbenchRagEvalQuestion(
            question_id="question-1",
            run_id="run-1",
            project_id="project-1",
            expected_runtime_entry_id="entry-1",
            expected_fact_id="fact-1",
            question="Как оформить заказ?",
            question_kind=WorkbenchRagEvalQuestionKind.ACTION_FIRST,
            source=WorkbenchRagEvalQuestionSource.GENERATED,
            generation_model="qwen/qwen3.6-27b",
            prompt_version="workbench_rag_eval_question_variants.ru.v2",
            contract_version="workbench_rag_eval_questions.v2",
            promotion_eligible=False,
            ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.MEDIUM,
            generation_rationale="Alias",
            generation_account_ref="groq_org_primary",
            generation_slot_index=0,
            status=WorkbenchRagEvalQuestionStatus.CREATED,
            created_at=_now(),
            evaluation_role=WorkbenchRagEvalQuestionRole.BASELINE,
        )
