from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
    WorkbenchRagEvalRetrievalOutcome,
)


def test_question_roles_are_exact_canonical_contract() -> None:
    assert tuple(role.value for role in WorkbenchRagEvalQuestionRole) == (
        "baseline",
        "promotion_pool",
        "holdout",
    )


def test_retrieval_classifications_are_exact_canonical_contract() -> None:
    assert tuple(
        classification.value
        for classification in WorkbenchRagEvalRetrievalClassification
    ) == (
        "pass_strong",
        "pass_weak",
        "confusion",
        "miss",
        "existing_alias_retrieval_failure",
    )


def test_retrieval_outcome_is_scoped_by_run_project_and_stage() -> None:
    outcome = WorkbenchRagEvalRetrievalOutcome(
        outcome_id="outcome-1",
        run_id="run-1",
        question_id="question-1",
        project_id="11111111-1111-1111-1111-111111111111",
        evaluation_stage="initial",
        expected_runtime_entry_id="runtime-entry-1",
        expected_fact_id="fact-1",
        expected_rank=1,
        expected_score=0.91,
        best_competitor_runtime_entry_id="runtime-entry-2",
        best_competitor_fact_id="fact-2",
        best_competitor_score=0.70,
        score_margin=0.21,
        classification=(WorkbenchRagEvalRetrievalClassification.PASS_STRONG),
        created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )

    assert outcome.run_id == "run-1"
    assert outcome.project_id == ("11111111-1111-1111-1111-111111111111")
    assert outcome.evaluation_stage == "initial"


@pytest.mark.parametrize(
    "filename,required_fragments,forbidden_fragments",
    (
        (
            "migrations/121_add_workbench_rag_eval_question_roles.sql",
            (
                "'baseline'",
                "'promotion_pool'",
                "'holdout'",
                "holdout_not_promotion_eligible",
                "baseline_not_promotion_eligible",
            ),
            (),
        ),
        (
            "migrations/122_create_workbench_rag_eval_retrieval_outcomes.sql",
            (
                "'pass_strong'",
                "'pass_weak'",
                "'confusion'",
                "'miss'",
                "'existing_alias_retrieval_failure'",
                "evaluation_stage",
                "UNIQUE",
            ),
            (
                "'top1'",
                "'top3'",
                "'top5'",
                "'confused_within_document'",
            ),
        ),
    ),
)
def test_migrations_enforce_canonical_contract(
    filename: str,
    required_fragments: tuple[str, ...],
    forbidden_fragments: tuple[str, ...],
) -> None:
    source = Path(filename).read_text(encoding="utf-8")

    for fragment in required_fragments:
        assert fragment in source

    for fragment in forbidden_fragments:
        assert fragment not in source


def test_rag_eval_python_does_not_reintroduce_wrong_classification_names() -> None:
    root = Path("src/contexts/knowledge_workbench/rag_eval")
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in root.rglob("*.py")
    )

    assert "CONFUSED_WITHIN_DOCUMENT" not in combined
    assert "RetrievalClassification.TOP1" not in combined
    assert "RetrievalClassification.TOP3" not in combined
    assert "RetrievalClassification.TOP5" not in combined
