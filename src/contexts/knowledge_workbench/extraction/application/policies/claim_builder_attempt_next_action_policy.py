from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_decision_policy import (
    ClaimBuilderAttemptDecision,
    ClaimBuilderAttemptOutcomeKind,
    ClaimBuilderNextModelStrategy,
)


class ClaimBuilderAttemptNextActionKind(Enum):
    PERSIST_VALID_CLAIMS = "PERSIST_VALID_CLAIMS"
    ACCEPT_VALID_EMPTY = "ACCEPT_VALID_EMPTY"
    RETRY_SAME_MODEL = "RETRY_SAME_MODEL"
    RETRY_FALLBACK_MODEL = "RETRY_FALLBACK_MODEL"
    RETRY_LARGER_OUTPUT_LIMIT_MODEL = "RETRY_LARGER_OUTPUT_LIMIT_MODEL"
    RETRY_LARGER_INPUT_LIMIT_MODEL = "RETRY_LARGER_INPUT_LIMIT_MODEL"
    SPLIT_SOURCE_UNIT = "SPLIT_SOURCE_UNIT"
    DEFER_UNTIL_CAPACITY_RESET = "DEFER_UNTIL_CAPACITY_RESET"
    PAUSE_FOR_DAILY_LIMIT_RESET = "PAUSE_FOR_DAILY_LIMIT_RESET"
    REQUEST_USER_LOW_QUALITY_CONTINUE_OR_WAIT = (
        "REQUEST_USER_LOW_QUALITY_CONTINUE_OR_WAIT"
    )
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


@dataclass(frozen=True, slots=True)
class ClaimBuilderAttemptNextAction:
    kind: ClaimBuilderAttemptNextActionKind
    reason: str
    next_model_strategy: ClaimBuilderNextModelStrategy | None
    run_after: datetime | None
    requires_source_split: bool
    should_persist_claims: bool
    should_mark_work_item_completed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ClaimBuilderAttemptNextActionKind):
            raise TypeError("kind must be ClaimBuilderAttemptNextActionKind")
        _require_non_empty_text(self.reason, "reason")
        if self.next_model_strategy is not None and not isinstance(
            self.next_model_strategy,
            ClaimBuilderNextModelStrategy,
        ):
            raise TypeError("next_model_strategy must be ClaimBuilderNextModelStrategy")
        if self.run_after is not None:
            _require_timezone_aware(self.run_after, "run_after")
        if not isinstance(self.requires_source_split, bool):
            raise TypeError("requires_source_split must be bool")
        if not isinstance(self.should_persist_claims, bool):
            raise TypeError("should_persist_claims must be bool")
        if not isinstance(self.should_mark_work_item_completed, bool):
            raise TypeError("should_mark_work_item_completed must be bool")

        if self.kind is ClaimBuilderAttemptNextActionKind.PERSIST_VALID_CLAIMS:
            if not self.should_persist_claims:
                raise ValueError("PERSIST_VALID_CLAIMS must persist claims")
            if not self.should_mark_work_item_completed:
                raise ValueError("PERSIST_VALID_CLAIMS must mark work item completed")
        if self.kind is ClaimBuilderAttemptNextActionKind.ACCEPT_VALID_EMPTY:
            if self.should_persist_claims:
                raise ValueError("ACCEPT_VALID_EMPTY must not persist claims")
            if not self.should_mark_work_item_completed:
                raise ValueError("ACCEPT_VALID_EMPTY must mark work item completed")
        if self.kind in {
            ClaimBuilderAttemptNextActionKind.RETRY_SAME_MODEL,
            ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL,
            ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL,
            ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL,
            ClaimBuilderAttemptNextActionKind.SPLIT_SOURCE_UNIT,
            ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET,
            ClaimBuilderAttemptNextActionKind.PAUSE_FOR_DAILY_LIMIT_RESET,
            ClaimBuilderAttemptNextActionKind.REQUEST_USER_LOW_QUALITY_CONTINUE_OR_WAIT,
            ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE,
        }:
            if self.should_persist_claims:
                raise ValueError("non-valid action must not persist claims")
            if self.should_mark_work_item_completed:
                raise ValueError("non-valid action must not mark work item completed")


class ClaimBuilderAttemptNextActionPolicy:
    def decide_next_action(
        self,
        decision: ClaimBuilderAttemptDecision,
    ) -> ClaimBuilderAttemptNextAction:
        if not isinstance(decision, ClaimBuilderAttemptDecision):
            raise TypeError("decision must be ClaimBuilderAttemptDecision")

        if decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.VALID_CLAIMS:
            return ClaimBuilderAttemptNextAction(
                kind=ClaimBuilderAttemptNextActionKind.PERSIST_VALID_CLAIMS,
                reason="valid_claims",
                next_model_strategy=None,
                run_after=None,
                requires_source_split=False,
                should_persist_claims=True,
                should_mark_work_item_completed=True,
            )

        if decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.VALID_EMPTY:
            return ClaimBuilderAttemptNextAction(
                kind=ClaimBuilderAttemptNextActionKind.ACCEPT_VALID_EMPTY,
                reason="valid_empty",
                next_model_strategy=None,
                run_after=None,
                requires_source_split=False,
                should_persist_claims=False,
                should_mark_work_item_completed=True,
            )

        if decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.RETRY_SAME_MODEL:
            return _retry_action(
                kind=ClaimBuilderAttemptNextActionKind.RETRY_SAME_MODEL,
                decision=decision,
                fallback_reason="retry_same_model",
            )

        if decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.RETRY_FALLBACK_MODEL:
            return _retry_action(
                kind=ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL,
                decision=decision,
                fallback_reason="retry_fallback_model",
            )

        if (
            decision.outcome_kind
            is ClaimBuilderAttemptOutcomeKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
        ):
            return _retry_action(
                kind=(
                    ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
                ),
                decision=decision,
                fallback_reason="retry_larger_output_limit_model",
            )

        if decision.outcome_kind is ClaimBuilderAttemptOutcomeKind.TERMINAL_INVALID:
            return ClaimBuilderAttemptNextAction(
                kind=ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE,
                reason=_reason(decision, fallback="terminal_invalid"),
                next_model_strategy=None,
                run_after=None,
                requires_source_split=False,
                should_persist_claims=False,
                should_mark_work_item_completed=False,
            )

        raise ValueError("unsupported claim builder attempt outcome kind")


def _retry_action(
    *,
    kind: ClaimBuilderAttemptNextActionKind,
    decision: ClaimBuilderAttemptDecision,
    fallback_reason: str,
) -> ClaimBuilderAttemptNextAction:
    return ClaimBuilderAttemptNextAction(
        kind=kind,
        reason=_reason(decision, fallback=fallback_reason),
        next_model_strategy=decision.next_model_strategy,
        run_after=None,
        requires_source_split=False,
        should_persist_claims=False,
        should_mark_work_item_completed=False,
    )


def _reason(decision: ClaimBuilderAttemptDecision, *, fallback: str) -> str:
    if decision.validation_failure_reason is not None:
        return decision.validation_failure_reason.value
    if decision.validation_decision is not None:
        return decision.validation_decision.value
    return fallback


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
