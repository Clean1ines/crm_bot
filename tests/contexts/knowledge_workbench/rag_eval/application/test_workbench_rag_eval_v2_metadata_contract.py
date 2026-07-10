from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionKind,
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
        == "qwen/qwen3-32b"
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
        generation_model="qwen/qwen3-32b",
        prompt_version="workbench_rag_eval_question_variants.ru.v2",
        contract_version="workbench_rag_eval_questions.v2",
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        generation_rationale="Однозначный action-first retrieval alias",
        generation_account_ref="groq_org_primary",
        generation_slot_index=0,
        status=WorkbenchRagEvalQuestionStatus.CREATED,
        created_at=_now(),
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
            generation_model="qwen/qwen3-32b",
            prompt_version="workbench_rag_eval_question_variants.ru.v2",
            contract_version="workbench_rag_eval_questions.v2",
            promotion_eligible=True,
            ambiguity_risk=risk,
            generation_rationale="Alias",
            generation_account_ref="groq_org_primary",
            generation_slot_index=0,
            status=WorkbenchRagEvalQuestionStatus.CREATED,
            created_at=_now(),
        )
