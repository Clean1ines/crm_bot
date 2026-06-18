from __future__ import annotations

import pytest

from src.shared.json_value import JsonInputValue
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationDecision,
    ClaimBuilderOutputValidationFailureReason,
    ClaimBuilderOutputValidationPolicy,
    ClaimBuilderOutputValidationResult,
    ValidateClaimBuilderOutputCommand,
    ValidatedClaimBuilderClaim,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)


SOURCE_UNIT_TEXT = (
    "Product System turns documents into knowledge. "
    "Pricing is not covered. "
    "Onboarding includes setup and import steps."
)


def _claim_payload(
    *,
    claim: JsonInputValue = "Product System turns documents into knowledge.",
    granularity: JsonInputValue = "atomic",
    possible_questions: JsonInputValue = ["Что делает Product System?"],
    exclusion_scope: JsonInputValue = "Цены не описаны.",
    evidence_block: JsonInputValue = "Product System turns documents into knowledge.",
) -> dict[str, JsonInputValue]:
    return {
        "claim": claim,
        "granularity": granularity,
        "possible_questions": possible_questions,
        "exclusion_scope": exclusion_scope,
        "evidence_block": evidence_block,
    }


def _validate(
    output_payload: JsonInputValue,
    *,
    source_unit_text: str = SOURCE_UNIT_TEXT,
    empty_claims_attempt_count: int = 0,
) -> ClaimBuilderOutputValidationResult:
    return ClaimBuilderOutputValidationPolicy().validate(
        ValidateClaimBuilderOutputCommand(
            output_payload=output_payload,
            source_unit_text=source_unit_text,
            empty_claims_attempt_count=empty_claims_attempt_count,
        )
    )


def _assert_failure(
    result: ClaimBuilderOutputValidationResult,
    *,
    decision: ClaimBuilderOutputValidationDecision = (
        ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL
    ),
    failure_reason: ClaimBuilderOutputValidationFailureReason,
) -> None:
    assert result.decision is decision
    assert result.claims == ()
    assert result.failure_reason is failure_reason


def test_valid_single_atomic_claim_returns_valid_claims() -> None:
    result = _validate({"claims": [_claim_payload()]})

    assert result.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS
    assert result.failure_reason is None
    assert result.claims == (
        ValidatedClaimBuilderClaim(
            claim="Product System turns documents into knowledge.",
            granularity=DraftClaimGranularity.ATOMIC,
            possible_questions=("Что делает Product System?",),
            exclusion_scope="Цены не описаны.",
            evidence_block="Product System turns documents into knowledge.",
        ),
    )


def test_empty_exclusion_scope_is_valid_when_prompt_requires_empty_string() -> None:
    result = _validate({"claims": [_claim_payload(exclusion_scope="")]})

    assert result.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS
    assert result.failure_reason is None
    assert result.claims[0].exclusion_scope == ""


def test_valid_multiple_claims_returns_valid_claims() -> None:
    result = _validate(
        {
            "claims": [
                _claim_payload(),
                _claim_payload(
                    claim="Onboarding includes setup and import steps.",
                    granularity="composite",
                    possible_questions=["Что включает Onboarding?"],
                    exclusion_scope="Цены не описаны.",
                    evidence_block="Onboarding includes setup and import steps.",
                ),
            ]
        }
    )

    assert result.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS
    assert tuple(claim.granularity for claim in result.claims) == (
        DraftClaimGranularity.ATOMIC,
        DraftClaimGranularity.COMPOSITE,
    )


def test_output_not_object_retries_same_model() -> None:
    result = _validate(["claims"])

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT,
    )


def test_claims_missing_retries_same_model() -> None:
    result = _validate({})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.CLAIMS_MISSING,
    )


def test_claims_not_list_retries_same_model() -> None:
    result = _validate({"claims": "not-list"})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.CLAIMS_NOT_LIST,
    )


def test_empty_claims_first_time_retries_same_model() -> None:
    result = _validate({"claims": []})

    _assert_failure(
        result,
        decision=ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED
        ),
    )


def test_empty_claims_after_same_model_retry_uses_fallback_check_model() -> None:
    result = _validate(
        {"claims": []},
        empty_claims_attempt_count=1,
    )

    _assert_failure(
        result,
        decision=(ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL),
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED
        ),
    )


def test_empty_claims_after_fallback_check_returns_valid_empty() -> None:
    result = _validate(
        {"claims": []},
        empty_claims_attempt_count=2,
    )

    assert result.decision is ClaimBuilderOutputValidationDecision.VALID_EMPTY
    assert result.claims == ()
    assert result.failure_reason is None


def test_claim_item_not_object_invalid() -> None:
    result = _validate({"claims": ["not-object"]})

    _assert_failure(
        result,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.CLAIM_ITEM_NOT_OBJECT
        ),
    )


def test_missing_field_invalid() -> None:
    claim = _claim_payload()
    del claim["evidence_block"]

    result = _validate({"claims": [claim]})

    _assert_failure(
        result,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_SET_INVALID
        ),
    )


def test_null_field_invalid() -> None:
    result = _validate({"claims": [_claim_payload(claim=None)]})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_NULL,
    )


def test_empty_claim_invalid() -> None:
    result = _validate({"claims": [_claim_payload(claim="  ")]})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.CLAIM_TEXT_EMPTY,
    )


def test_empty_evidence_invalid() -> None:
    result = _validate({"claims": [_claim_payload(evidence_block="  ")]})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.EVIDENCE_BLOCK_EMPTY,
    )


def test_evidence_block_not_exact_source_excerpt_invalid() -> None:
    result = _validate(
        {
            "claims": [
                _claim_payload(
                    evidence_block="Product System almost turns documents into knowledge."
                )
            ]
        }
    )

    _assert_failure(
        result,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.EVIDENCE_BLOCK_NOT_SOURCE_EXCERPT
        ),
    )


def test_latin_in_claim_allowed_when_token_exists_in_evidence_block() -> None:
    result = _validate({"claims": [_claim_payload()]})

    assert result.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS


def test_latin_in_claim_rejected_when_token_absent_in_evidence_block() -> None:
    result = _validate(
        {
            "claims": [
                _claim_payload(
                    claim="Product System uses OpenAI.",
                    evidence_block="Product System turns documents into knowledge.",
                    possible_questions=["Что делает Product System?"],
                )
            ]
        }
    )

    _assert_failure(
        result,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE
        ),
    )


def test_latin_in_possible_questions_rejected_when_token_absent_in_evidence_block() -> (
    None
):
    result = _validate(
        {
            "claims": [
                _claim_payload(
                    possible_questions=["Does Product System use OpenAI?"],
                    evidence_block="Product System turns documents into knowledge.",
                )
            ]
        }
    )

    _assert_failure(
        result,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE
        ),
    )


def test_possible_questions_non_list_invalid() -> None:
    result = _validate({"claims": [_claim_payload(possible_questions=("Question?",))]})

    _assert_failure(
        result,
        failure_reason=(
            ClaimBuilderOutputValidationFailureReason.POSSIBLE_QUESTIONS_NOT_LIST
        ),
    )


def test_possible_questions_empty_string_invalid() -> None:
    result = _validate({"claims": [_claim_payload(possible_questions=[""])]})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.POSSIBLE_QUESTION_EMPTY,
    )


def test_invalid_granularity_invalid() -> None:
    result = _validate({"claims": [_claim_payload(granularity="global")]})

    _assert_failure(
        result,
        failure_reason=ClaimBuilderOutputValidationFailureReason.GRANULARITY_INVALID,
    )


@pytest.mark.parametrize(
    ("decision", "claims", "failure_reason"),
    (
        (
            ClaimBuilderOutputValidationDecision.VALID_CLAIMS,
            (),
            None,
        ),
        (
            ClaimBuilderOutputValidationDecision.VALID_EMPTY,
            (
                ValidatedClaimBuilderClaim(
                    claim="Product System turns documents into knowledge.",
                    granularity=DraftClaimGranularity.ATOMIC,
                    possible_questions=("Что делает Product System?",),
                    exclusion_scope="Цены не описаны.",
                    evidence_block="Product System turns documents into knowledge.",
                ),
            ),
            None,
        ),
        (
            ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            (),
            None,
        ),
    ),
)
def test_validation_result_invariants(
    decision: ClaimBuilderOutputValidationDecision,
    claims: tuple[ValidatedClaimBuilderClaim, ...],
    failure_reason: ClaimBuilderOutputValidationFailureReason | None,
) -> None:
    with pytest.raises(ValueError):
        ClaimBuilderOutputValidationResult(
            decision=decision,
            claims=claims,
            failure_reason=failure_reason,
        )
