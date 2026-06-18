from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_decision_policy import (
    ClaimBuilderAttemptDecision,
    ClaimBuilderAttemptOutcomeKind,
    ClaimBuilderNextModelStrategy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_next_action_policy import (
    ClaimBuilderAttemptNextActionKind,
    ClaimBuilderAttemptNextActionPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationDecision,
    ClaimBuilderOutputValidationFailureReason,
    ValidatedClaimBuilderClaim,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)


def _validated_claim() -> ValidatedClaimBuilderClaim:
    return ValidatedClaimBuilderClaim(
        claim="Product System turns documents into knowledge.",
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=("Что делает Product System?",),
        exclusion_scope="Цены не описаны.",
        evidence_block="Product System turns documents into knowledge.",
    )


def _decision(
    *,
    outcome_kind: ClaimBuilderAttemptOutcomeKind,
    validation_decision: ClaimBuilderOutputValidationDecision | None,
    validation_failure_reason: ClaimBuilderOutputValidationFailureReason | None,
    claims: tuple[ValidatedClaimBuilderClaim, ...] = (),
    next_model_strategy: ClaimBuilderNextModelStrategy | None = None,
    retry_recommended: bool = False,
) -> ClaimBuilderAttemptDecision:
    return ClaimBuilderAttemptDecision(
        outcome_kind=outcome_kind,
        validation_decision=validation_decision,
        validation_failure_reason=validation_failure_reason,
        claims=claims,
        next_model_strategy=next_model_strategy,
        retry_recommended=retry_recommended,
    )


def _action(decision: ClaimBuilderAttemptDecision):
    return ClaimBuilderAttemptNextActionPolicy().decide_next_action(decision)


def test_valid_claims_maps_to_persist_valid_claims() -> None:
    action = _action(
        _decision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.VALID_CLAIMS,
            validation_decision=ClaimBuilderOutputValidationDecision.VALID_CLAIMS,
            validation_failure_reason=None,
            claims=(_validated_claim(),),
        )
    )

    assert action.kind is ClaimBuilderAttemptNextActionKind.PERSIST_VALID_CLAIMS
    assert action.should_persist_claims is True
    assert action.should_mark_work_item_completed is True
    assert action.requires_source_split is False
    assert action.next_model_strategy is None


def test_valid_empty_maps_to_accept_valid_empty() -> None:
    action = _action(
        _decision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.VALID_EMPTY,
            validation_decision=ClaimBuilderOutputValidationDecision.VALID_EMPTY,
            validation_failure_reason=None,
        )
    )

    assert action.kind is ClaimBuilderAttemptNextActionKind.ACCEPT_VALID_EMPTY
    assert action.should_persist_claims is False
    assert action.should_mark_work_item_completed is True


def test_retry_same_model_maps_to_retry_same_model() -> None:
    action = _action(
        _decision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL,
            validation_decision=ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL,
            validation_failure_reason=(
                ClaimBuilderOutputValidationFailureReason.CLAIMS_MISSING
            ),
            next_model_strategy=ClaimBuilderNextModelStrategy.SAME_MODEL,
            retry_recommended=True,
        )
    )

    assert action.kind is ClaimBuilderAttemptNextActionKind.RETRY_SAME_MODEL
    assert action.reason == "CLAIMS_MISSING"
    assert action.next_model_strategy is ClaimBuilderNextModelStrategy.SAME_MODEL
    assert action.should_mark_work_item_completed is False


def test_retry_empty_claims_check_model_maps_to_explicit_check_action() -> None:
    action = _action(
        _decision(
            outcome_kind=(
                ClaimBuilderAttemptOutcomeKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL
            ),
            validation_decision=(
                ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL
            ),
            validation_failure_reason=(
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED
            ),
            next_model_strategy=(
                ClaimBuilderNextModelStrategy.EMPTY_CLAIMS_CHECK_MODEL_REQUIRED
            ),
            retry_recommended=True,
        )
    )

    assert action.kind is (
        ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL
    )
    assert action.next_model_strategy is (
        ClaimBuilderNextModelStrategy.EMPTY_CLAIMS_CHECK_MODEL_REQUIRED
    )
    assert action.should_mark_work_item_completed is False


def test_retry_larger_output_limit_model_maps_to_larger_output_action() -> None:
    action = _action(
        _decision(
            outcome_kind=(
                ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
            ),
            validation_decision=(
                ClaimBuilderOutputValidationDecision.RETRY_LARGER_OUTPUT_LIMIT_MODEL
            ),
            validation_failure_reason=(
                ClaimBuilderOutputValidationFailureReason.TRUNCATED_JSON_RETRY_REQUIRED
            ),
            next_model_strategy=(
                ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED
            ),
            retry_recommended=True,
        )
    )

    assert action.kind is (
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
    )
    assert action.next_model_strategy is (
        ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED
    )
    assert action.should_mark_work_item_completed is False


def test_retry_larger_input_limit_model_maps_to_larger_input_action() -> None:
    action = _action(
        _decision(
            outcome_kind=(
                ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_INPUT_LIMIT_MODEL
            ),
            validation_decision=None,
            validation_failure_reason=(
                ClaimBuilderOutputValidationFailureReason.CLAIMS_MISSING
            ),
            next_model_strategy=(
                ClaimBuilderNextModelStrategy.LARGER_INPUT_LIMIT_MODEL_REQUIRED
            ),
            retry_recommended=True,
        )
    )

    assert action.kind is (
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL
    )
    assert action.next_model_strategy is (
        ClaimBuilderNextModelStrategy.LARGER_INPUT_LIMIT_MODEL_REQUIRED
    )
    assert action.should_mark_work_item_completed is False


def test_terminal_invalid_maps_to_terminal_failure_without_completion() -> None:
    action = _action(
        _decision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.TERMINAL_INVALID,
            validation_decision=ClaimBuilderOutputValidationDecision.TERMINAL_INVALID,
            validation_failure_reason=(
                ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_SET_INVALID
            ),
        )
    )

    assert action.kind is ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE
    assert action.should_persist_claims is False
    assert action.should_mark_work_item_completed is False


def test_reserved_enum_values_exist_for_later_application_flow() -> None:
    assert ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
    assert ClaimBuilderAttemptNextActionKind.SPLIT_SOURCE_UNIT.value
    assert ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
    assert ClaimBuilderAttemptNextActionKind.PAUSE_FOR_DAILY_LIMIT_RESET.value
    assert ClaimBuilderAttemptNextActionKind.REQUEST_USER_LOW_QUALITY_CONTINUE_OR_WAIT.value
