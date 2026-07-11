from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_role_policy import (
    WorkbenchRagEvalQuestionRolePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_retrieval_outcome_policy import (
    WorkbenchRagEvalRetrievalOutcomePolicy,
)


def test_roles_are_deterministic_and_at_least_twenty_percent_holdout() -> None:
    policy = WorkbenchRagEvalQuestionRolePolicy()
    first = policy.assign(
        entry_id="entry-1", question_ids=tuple(f"q-{i}" for i in range(10))
    )
    assert first == policy.assign(
        entry_id="entry-1", question_ids=tuple(f"q-{i}" for i in range(10))
    )
    assert (
        sum(role is WorkbenchRagEvalQuestionRole.HOLDOUT for role in first.values())
        >= 2
    )
    assert (
        sum(
            role is WorkbenchRagEvalQuestionRole.PROMOTION_POOL
            for role in first.values()
        )
        == 8
    )


def test_holdout_is_never_promotion_eligible() -> None:
    assert (
        WorkbenchRagEvalQuestionRolePolicy().promotion_eligible(
            role=WorkbenchRagEvalQuestionRole.HOLDOUT, generated_eligible=True
        )
        is False
    )


def test_retrieval_policy_classifies_all_five_with_confusion_precedence() -> None:
    policy = WorkbenchRagEvalRetrievalOutcomePolicy()
    assert (
        policy.classify(
            expected_rank=1,
            expected_score=0.9,
            competitor_score=0.2,
            competitor_same_document=False,
        )
        is WorkbenchRagEvalRetrievalClassification.PASS_STRONG
    )
    assert (
        policy.classify(
            expected_rank=3,
            expected_score=0.7,
            competitor_score=0.8,
            competitor_same_document=False,
        )
        is WorkbenchRagEvalRetrievalClassification.PASS_WEAK
    )
    assert (
        policy.classify(
            expected_rank=5,
            expected_score=0.6,
            competitor_score=0.8,
            competitor_same_document=False,
        )
        is WorkbenchRagEvalRetrievalClassification.CONFUSION
    )
    assert (
        policy.classify(
            expected_rank=None,
            expected_score=None,
            competitor_score=0.8,
            competitor_same_document=True,
        )
        is WorkbenchRagEvalRetrievalClassification.CONFUSION
    )
    assert (
        policy.classify(
            expected_rank=4,
            expected_score=0.5,
            competitor_score=0.8,
            competitor_same_document=True,
        )
        is WorkbenchRagEvalRetrievalClassification.CONFUSION
    )
    assert (
        policy.classify(
            expected_rank=None,
            expected_score=None,
            competitor_score=0.8,
            competitor_same_document=False,
        )
        is WorkbenchRagEvalRetrievalClassification.MISS
    )


def test_outcome_calculates_exact_margin() -> None:
    outcome = WorkbenchRagEvalRetrievalOutcomePolicy().build(
        outcome_id="outcome-run-1-q-initial",
        run_id="run-1",
        question_id="q",
        project_id="11111111-1111-1111-1111-111111111111",
        evaluation_stage="initial",
        expected_runtime_entry_id="e",
        expected_fact_id="f",
        expected_rank=2,
        expected_score=0.75,
        best_competitor_runtime_entry_id="c",
        best_competitor_fact_id="cf",
        best_competitor_score=0.55,
        competitor_same_document=False,
    )
    assert outcome.score_margin == 0.75 - 0.55
