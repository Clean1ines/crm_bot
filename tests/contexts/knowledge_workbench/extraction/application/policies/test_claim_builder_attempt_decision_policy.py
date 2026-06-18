from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_decision_policy import (
    ClaimBuilderAttemptDecisionPolicy,
    ClaimBuilderAttemptOutcomeKind,
    ClaimBuilderNextModelStrategy,
    DecideClaimBuilderAttemptOutcomeCommand,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationDecision,
    ClaimBuilderOutputValidationFailureReason,
    ClaimBuilderOutputValidationPolicy,
    ValidateClaimBuilderOutputCommand,
)


SOURCE_UNIT_TEXT = "Product System turns documents into knowledge. Цены не описаны."


def _valid_payload() -> dict[str, object]:
    return {
        "claims": [
            {
                "claim": "Product System turns documents into knowledge.",
                "granularity": "atomic",
                "possible_questions": ["Что делает Product System?"],
                "exclusion_scope": "Цены не описаны.",
                "evidence_block": "Product System turns documents into knowledge.",
            }
        ]
    }


def _validation(
    payload: dict[str, object],
    *,
    empty_claims_attempt_count: int = 0,
):
    return ClaimBuilderOutputValidationPolicy().validate(
        ValidateClaimBuilderOutputCommand(
            output_payload=payload,
            source_unit_text=SOURCE_UNIT_TEXT,
            empty_claims_attempt_count=empty_claims_attempt_count,
        )
    )


def _command(
    *,
    output_payload: dict[str, object] | None = None,
    raw_output_text: str | None = "{}",
    is_output_truncated: bool = False,
    validation_result=None,
) -> DecideClaimBuilderAttemptOutcomeCommand:
    return DecideClaimBuilderAttemptOutcomeCommand(
        workflow_run_id="workflow-1",
        work_item_id="work-1",
        dispatch_attempt_id="work-1:attempt:1",
        attempt_number=1,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        output_payload=output_payload,
        raw_output_text=raw_output_text,
        source_unit_text=SOURCE_UNIT_TEXT,
        is_output_truncated=is_output_truncated,
        validation_result=validation_result,
    )


def test_empty_raw_output_retries_same_model() -> None:
    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(output_payload=None, raw_output_text=""),
    )

    assert decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL
    assert decision.next_model_strategy is ClaimBuilderNextModelStrategy.SAME_MODEL
    assert decision.retry_recommended is True


def test_invalid_json_marker_retries_same_model() -> None:
    validation_result = _validation({"bad": []})

    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(validation_result=validation_result),
    )

    assert decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL
    assert decision.validation_failure_reason is (
        ClaimBuilderOutputValidationFailureReason.CLAIMS_MISSING
    )


def test_truncated_output_retries_larger_output_model() -> None:
    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(is_output_truncated=True),
    )

    assert decision.outcome_kind is (
        ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
    )
    assert decision.next_model_strategy is (
        ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED
    )
    assert decision.validation_failure_reason is (
        ClaimBuilderOutputValidationFailureReason.TRUNCATED_JSON_RETRY_REQUIRED
    )


def test_empty_claims_first_time_retries_same_model() -> None:
    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(validation_result=_validation({"claims": []})),
    )

    assert decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL
    assert decision.validation_decision is (
        ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL
    )
    assert decision.next_model_strategy is ClaimBuilderNextModelStrategy.SAME_MODEL


def test_empty_claims_after_same_model_retry_uses_fallback_check_model() -> None:
    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(
            validation_result=_validation(
                {"claims": []},
                empty_claims_attempt_count=1,
            )
        ),
    )

    assert decision.outcome_kind is (
        ClaimBuilderAttemptOutcomeKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL
    )
    assert decision.validation_decision is (
        ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL
    )
    assert decision.next_model_strategy is (
        ClaimBuilderNextModelStrategy.EMPTY_CLAIMS_CHECK_MODEL_REQUIRED
    )


def test_empty_claims_after_fallback_check_is_valid_empty() -> None:
    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(
            validation_result=_validation(
                {"claims": []},
                empty_claims_attempt_count=2,
            )
        ),
    )

    assert decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.VALID_EMPTY
    assert decision.claims == ()
    assert decision.retry_recommended is False


def test_latin_evidence_failure_retries_with_exact_reason() -> None:
    validation_result = _validation(
        {
            "claims": [
                {
                    "claim": "Product System uses OpenAI.",
                    "granularity": "atomic",
                    "possible_questions": ["Что делает Product System?"],
                    "exclusion_scope": "Цены не описаны.",
                    "evidence_block": "Product System turns documents into knowledge.",
                }
            ]
        }
    )

    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(validation_result=validation_result),
    )

    assert decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL
    assert decision.validation_failure_reason is (
        ClaimBuilderOutputValidationFailureReason.LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE
    )


def test_valid_claims_are_carried() -> None:
    decision = ClaimBuilderAttemptDecisionPolicy().decide(
        _command(
            output_payload=_valid_payload(),
            validation_result=_validation(_valid_payload()),
        ),
    )

    assert decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.VALID_CLAIMS
    assert len(decision.claims) == 1
    assert decision.claims[0].claim == "Product System turns documents into knowledge."
