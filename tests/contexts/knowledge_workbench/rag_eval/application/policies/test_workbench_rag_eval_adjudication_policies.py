from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_adjudication_policy import (
    WorkbenchRagEvalAdjudicationEligibilityPolicy,
    WorkbenchRagEvalAdjudicationPromotionCandidatePolicy,
    WorkbenchRagEvalAdjudicationVerdict,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_adjudication_output_validation_policy import (
    WorkbenchRagEvalAdjudicationOutputValidationOutcome,
    WorkbenchRagEvalAdjudicationOutputValidationPolicy,
)


@pytest.mark.parametrize(
    "classification",
    (
        WorkbenchRagEvalRetrievalClassification.MISS,
        WorkbenchRagEvalRetrievalClassification.CONFUSION,
        WorkbenchRagEvalRetrievalClassification.PASS_WEAK,
    ),
)
def test_adjudication_eligibility_includes_configured_failures(
    classification: WorkbenchRagEvalRetrievalClassification,
) -> None:
    assert WorkbenchRagEvalAdjudicationEligibilityPolicy.default().is_eligible(
        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        classification=classification,
    )


@pytest.mark.parametrize(
    (
        "role",
        "promotion_eligible",
        "risk",
        "classification",
    ),
    (
        (
            WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
            True,
            WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
            WorkbenchRagEvalRetrievalClassification.PASS_STRONG,
        ),
        (
            WorkbenchRagEvalQuestionRole.BASELINE,
            True,
            WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
            WorkbenchRagEvalRetrievalClassification.MISS,
        ),
        (
            WorkbenchRagEvalQuestionRole.HOLDOUT,
            True,
            WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
            WorkbenchRagEvalRetrievalClassification.MISS,
        ),
        (
            WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
            True,
            WorkbenchRagEvalQuestionAmbiguityRisk.MEDIUM,
            WorkbenchRagEvalRetrievalClassification.MISS,
        ),
        (
            WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
            True,
            WorkbenchRagEvalQuestionAmbiguityRisk.HIGH,
            WorkbenchRagEvalRetrievalClassification.MISS,
        ),
        (
            WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
            False,
            WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
            WorkbenchRagEvalRetrievalClassification.MISS,
        ),
        (
            WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
            True,
            WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
            WorkbenchRagEvalRetrievalClassification.EXISTING_ALIAS_RETRIEVAL_FAILURE,
        ),
    ),
)
def test_adjudication_eligibility_excludes_forbidden_questions(
    role: WorkbenchRagEvalQuestionRole,
    promotion_eligible: bool,
    risk: WorkbenchRagEvalQuestionAmbiguityRisk,
    classification: WorkbenchRagEvalRetrievalClassification,
) -> None:
    assert not WorkbenchRagEvalAdjudicationEligibilityPolicy.default().is_eligible(
        evaluation_role=role,
        promotion_eligible=promotion_eligible,
        ambiguity_risk=risk,
        classification=classification,
    )


@pytest.mark.parametrize(
    "verdict",
    tuple(WorkbenchRagEvalAdjudicationVerdict),
)
def test_adjudication_output_validation_accepts_all_canonical_verdicts(
    verdict: WorkbenchRagEvalAdjudicationVerdict,
) -> None:
    result = WorkbenchRagEvalAdjudicationOutputValidationPolicy().validate(
        raw_text=(
            "{"
            '"contract_version":"workbench_rag_eval_adjudication.v1",'
            f'"verdict":"{verdict.value}",'
            f'"promotion_recommended":{str(verdict is WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY).lower()},'
            '"reason":"Достаточное объяснение."'
            "}"
        )
    )

    assert (
        result.outcome
        is WorkbenchRagEvalAdjudicationOutputValidationOutcome.VALID_ADJUDICATION
    )
    assert result.adjudication is not None
    assert result.adjudication.verdict is verdict


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    (
        ("not-json", WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_JSON),
        ("[]", WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_ROOT),
        (
            '{"contract_version":"old","verdict":"valid_target_query","promotion_recommended":true,"reason":"ok"}',
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_CONTRACT_VERSION,
        ),
        (
            '{"contract_version":"workbench_rag_eval_adjudication.v1","verdict":"bad","promotion_recommended":false,"reason":"ok"}',
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_VERDICT,
        ),
        (
            '{"contract_version":"workbench_rag_eval_adjudication.v1","verdict":"ambiguous","promotion_recommended":true,"reason":"ok"}',
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_PROMOTION_RECOMMENDATION,
        ),
        (
            '{"contract_version":"workbench_rag_eval_adjudication.v1","verdict":"valid_target_query","promotion_recommended":true,"reason":"  "}',
            WorkbenchRagEvalAdjudicationOutputValidationOutcome.INVALID_REASON,
        ),
    ),
)
def test_adjudication_output_validation_rejects_contract_violations(
    raw_text: str,
    expected: WorkbenchRagEvalAdjudicationOutputValidationOutcome,
) -> None:
    result = WorkbenchRagEvalAdjudicationOutputValidationPolicy().validate(
        raw_text=raw_text
    )

    assert result.outcome is expected
    assert result.adjudication is None


def test_candidate_policy_requires_valid_target_query_recommendation() -> None:
    policy = WorkbenchRagEvalAdjudicationPromotionCandidatePolicy.default()

    assert policy.should_create_candidate(
        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        classification=WorkbenchRagEvalRetrievalClassification.MISS,
        verdict=WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY,
        promotion_recommended=True,
    )
    assert not policy.should_create_candidate(
        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        classification=WorkbenchRagEvalRetrievalClassification.MISS,
        verdict=WorkbenchRagEvalAdjudicationVerdict.AMBIGUOUS,
        promotion_recommended=False,
    )
    assert not policy.should_create_candidate(
        evaluation_role=WorkbenchRagEvalQuestionRole.HOLDOUT,
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        classification=WorkbenchRagEvalRetrievalClassification.MISS,
        verdict=WorkbenchRagEvalAdjudicationVerdict.VALID_TARGET_QUERY,
        promotion_recommended=True,
    )
