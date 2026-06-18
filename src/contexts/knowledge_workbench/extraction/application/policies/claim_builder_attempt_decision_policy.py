from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.shared.json_value import JsonInputValue
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationDecision,
    ClaimBuilderOutputValidationFailureReason,
    ClaimBuilderOutputValidationResult,
    ValidatedClaimBuilderClaim,
)


class ClaimBuilderAttemptOutcomeKind(Enum):
    VALID_CLAIMS = "VALID_CLAIMS"
    VALID_EMPTY = "VALID_EMPTY"
    RETRY_SAME_MODEL = "RETRY_SAME_MODEL"
    RETRY_EMPTY_CLAIMS_CHECK_MODEL = "RETRY_EMPTY_CLAIMS_CHECK_MODEL"
    RETRY_FALLBACK_MODEL = "RETRY_FALLBACK_MODEL"
    RETRY_LARGER_INPUT_LIMIT_MODEL = "RETRY_LARGER_INPUT_LIMIT_MODEL"
    RETRY_LARGER_OUTPUT_LIMIT_MODEL = "RETRY_LARGER_OUTPUT_LIMIT_MODEL"
    TERMINAL_INVALID = "TERMINAL_INVALID"


class ClaimBuilderNextModelStrategy(Enum):
    SAME_MODEL = "SAME_MODEL"
    EMPTY_CLAIMS_CHECK_MODEL_REQUIRED = "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"
    FALLBACK_MODEL_REQUIRED = "FALLBACK_MODEL_REQUIRED"
    LARGER_INPUT_LIMIT_MODEL_REQUIRED = "LARGER_INPUT_LIMIT_MODEL_REQUIRED"
    LARGER_OUTPUT_LIMIT_MODEL_REQUIRED = "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"


@dataclass(frozen=True, slots=True)
class DecideClaimBuilderAttemptOutcomeCommand:
    workflow_run_id: str
    work_item_id: str
    dispatch_attempt_id: str
    attempt_number: int
    provider: str
    model_ref: str
    output_payload: JsonInputValue | None
    raw_output_text: str | None
    source_unit_text: str
    is_output_truncated: bool
    validation_result: ClaimBuilderOutputValidationResult | None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.dispatch_attempt_id, "dispatch_attempt_id")
        _require_non_empty_text(self.provider, "provider")
        _require_non_empty_text(self.model_ref, "model_ref")
        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")
        if not isinstance(self.source_unit_text, str):
            raise TypeError("source_unit_text must be str")
        if not isinstance(self.is_output_truncated, bool):
            raise TypeError("is_output_truncated must be bool")
        if self.validation_result is not None and not isinstance(
            self.validation_result,
            ClaimBuilderOutputValidationResult,
        ):
            raise TypeError(
                "validation_result must be ClaimBuilderOutputValidationResult",
            )


@dataclass(frozen=True, slots=True)
class ClaimBuilderAttemptDecision:
    outcome_kind: ClaimBuilderAttemptOutcomeKind
    validation_decision: ClaimBuilderOutputValidationDecision | None
    validation_failure_reason: ClaimBuilderOutputValidationFailureReason | None
    claims: tuple[ValidatedClaimBuilderClaim, ...]
    next_model_strategy: ClaimBuilderNextModelStrategy | None
    retry_recommended: bool

    def __post_init__(self) -> None:
        if not isinstance(self.outcome_kind, ClaimBuilderAttemptOutcomeKind):
            raise TypeError("outcome_kind must be ClaimBuilderAttemptOutcomeKind")
        if self.validation_decision is not None and not isinstance(
            self.validation_decision,
            ClaimBuilderOutputValidationDecision,
        ):
            raise TypeError(
                "validation_decision must be ClaimBuilderOutputValidationDecision",
            )
        if self.validation_failure_reason is not None and not isinstance(
            self.validation_failure_reason,
            ClaimBuilderOutputValidationFailureReason,
        ):
            raise TypeError(
                "validation_failure_reason must be ClaimBuilderOutputValidationFailureReason",
            )
        if not isinstance(self.claims, tuple):
            raise TypeError("claims must be tuple")
        for claim in self.claims:
            if not isinstance(claim, ValidatedClaimBuilderClaim):
                raise TypeError("claims must contain ValidatedClaimBuilderClaim")
        if self.next_model_strategy is not None and not isinstance(
            self.next_model_strategy,
            ClaimBuilderNextModelStrategy,
        ):
            raise TypeError("next_model_strategy must be ClaimBuilderNextModelStrategy")
        if not isinstance(self.retry_recommended, bool):
            raise TypeError("retry_recommended must be bool")

        if self.outcome_kind is ClaimBuilderAttemptOutcomeKind.VALID_CLAIMS:
            if not self.claims:
                raise ValueError("VALID_CLAIMS requires non-empty claims")
            if self.validation_failure_reason is not None:
                raise ValueError("VALID_CLAIMS requires no failure reason")
            if self.retry_recommended:
                raise ValueError("VALID_CLAIMS must not recommend retry")
            return

        if self.outcome_kind is ClaimBuilderAttemptOutcomeKind.VALID_EMPTY:
            if self.claims:
                raise ValueError("VALID_EMPTY requires empty claims")
            if self.validation_failure_reason is not None:
                raise ValueError("VALID_EMPTY requires no failure reason")
            if self.retry_recommended:
                raise ValueError("VALID_EMPTY must not recommend retry")
            return

        if self.claims:
            raise ValueError("retry/terminal decisions require empty claims")
        if self.validation_failure_reason is None:
            raise ValueError("retry/terminal decisions require failure reason")


class ClaimBuilderAttemptDecisionPolicy:
    def decide(
        self,
        command: DecideClaimBuilderAttemptOutcomeCommand,
    ) -> ClaimBuilderAttemptDecision:
        if command.is_output_truncated:
            return ClaimBuilderAttemptDecision(
                outcome_kind=(
                    ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
                ),
                validation_decision=(
                    ClaimBuilderOutputValidationDecision.RETRY_LARGER_OUTPUT_LIMIT_MODEL
                ),
                validation_failure_reason=(
                    ClaimBuilderOutputValidationFailureReason.TRUNCATED_JSON_RETRY_REQUIRED
                ),
                claims=(),
                next_model_strategy=(
                    ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED
                ),
                retry_recommended=True,
            )

        if (
            _raw_output_missing(command.raw_output_text)
            and command.output_payload is None
        ):
            return ClaimBuilderAttemptDecision(
                outcome_kind=ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL,
                validation_decision=(
                    ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL
                ),
                validation_failure_reason=(
                    ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT
                ),
                claims=(),
                next_model_strategy=ClaimBuilderNextModelStrategy.SAME_MODEL,
                retry_recommended=True,
            )

        if command.validation_result is None:
            return ClaimBuilderAttemptDecision(
                outcome_kind=ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL,
                validation_decision=(
                    ClaimBuilderOutputValidationDecision.RETRY_SAME_MODEL
                ),
                validation_failure_reason=(
                    ClaimBuilderOutputValidationFailureReason.OUTPUT_NOT_OBJECT
                ),
                claims=(),
                next_model_strategy=ClaimBuilderNextModelStrategy.SAME_MODEL,
                retry_recommended=True,
            )

        return _decision_from_validation(command.validation_result)


def _decision_from_validation(
    validation_result: ClaimBuilderOutputValidationResult,
) -> ClaimBuilderAttemptDecision:
    if validation_result.decision is ClaimBuilderOutputValidationDecision.VALID_CLAIMS:
        return ClaimBuilderAttemptDecision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.VALID_CLAIMS,
            validation_decision=validation_result.decision,
            validation_failure_reason=None,
            claims=validation_result.claims,
            next_model_strategy=None,
            retry_recommended=False,
        )

    if validation_result.decision is ClaimBuilderOutputValidationDecision.VALID_EMPTY:
        return ClaimBuilderAttemptDecision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.VALID_EMPTY,
            validation_decision=validation_result.decision,
            validation_failure_reason=None,
            claims=(),
            next_model_strategy=None,
            retry_recommended=False,
        )

    if (
        validation_result.decision
        is ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL
    ):
        return _retry_decision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL,
            validation_result=validation_result,
            strategy=ClaimBuilderNextModelStrategy.EMPTY_CLAIMS_CHECK_MODEL_REQUIRED,
        )

    if (
        validation_result.decision
        is ClaimBuilderOutputValidationDecision.RETRY_FALLBACK_MODEL
    ):
        return _retry_decision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.RETRY_FALLBACK_MODEL,
            validation_result=validation_result,
            strategy=ClaimBuilderNextModelStrategy.FALLBACK_MODEL_REQUIRED,
        )

    if (
        validation_result.decision
        is ClaimBuilderOutputValidationDecision.RETRY_LARGER_OUTPUT_LIMIT_MODEL
    ):
        return _retry_decision(
            outcome_kind=(
                ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
            ),
            validation_result=validation_result,
            strategy=ClaimBuilderNextModelStrategy.LARGER_OUTPUT_LIMIT_MODEL_REQUIRED,
        )

    if (
        validation_result.decision
        is ClaimBuilderOutputValidationDecision.TERMINAL_INVALID
    ):
        return ClaimBuilderAttemptDecision(
            outcome_kind=ClaimBuilderAttemptOutcomeKind.TERMINAL_INVALID,
            validation_decision=validation_result.decision,
            validation_failure_reason=validation_result.failure_reason,
            claims=(),
            next_model_strategy=None,
            retry_recommended=False,
        )

    return _retry_decision(
        outcome_kind=ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL,
        validation_result=validation_result,
        strategy=ClaimBuilderNextModelStrategy.SAME_MODEL,
    )


def _retry_decision(
    *,
    outcome_kind: ClaimBuilderAttemptOutcomeKind,
    validation_result: ClaimBuilderOutputValidationResult,
    strategy: ClaimBuilderNextModelStrategy,
) -> ClaimBuilderAttemptDecision:
    return ClaimBuilderAttemptDecision(
        outcome_kind=outcome_kind,
        validation_decision=validation_result.decision,
        validation_failure_reason=validation_result.failure_reason,
        claims=(),
        next_model_strategy=strategy,
        retry_recommended=True,
    )


def _raw_output_missing(raw_output_text: str | None) -> bool:
    return raw_output_text is None or not raw_output_text.strip()


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
