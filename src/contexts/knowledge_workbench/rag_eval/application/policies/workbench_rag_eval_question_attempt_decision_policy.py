from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkbenchRagEvalQuestionAttemptDecisionKind(StrEnum):
    RETRY_SAME_ROUTE = "RETRY_SAME_ROUTE"
    RETRY_FALLBACK_ROUTE = "RETRY_FALLBACK_ROUTE"
    WAIT_CAPACITY_WINDOW = "WAIT_CAPACITY_WINDOW"
    RETRY_LARGER_INPUT_ROUTE = "RETRY_LARGER_INPUT_ROUTE"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True, slots=True)
class DecideWorkbenchRagEvalQuestionAttemptCommand:
    error_kind: str
    same_route_attempt_number: int
    same_route_retry_limit: int
    current_route_index: int
    route_count: int
    input_tokens: int
    next_route_input_limit: int | None

    def __post_init__(self) -> None:
        if not self.error_kind.strip():
            raise ValueError("error_kind must be non-empty")
        if self.same_route_attempt_number <= 0 or self.same_route_retry_limit <= 0:
            raise ValueError("attempt number and retry limit must be positive")
        if (
            self.current_route_index < 0
            or self.route_count <= 0
            or self.current_route_index >= self.route_count
        ):
            raise ValueError("current route must be within route count")
        if self.input_tokens < 0:
            raise ValueError("input_tokens must be non-negative")
        if self.next_route_input_limit is not None and self.next_route_input_limit <= 0:
            raise ValueError("next_route_input_limit must be positive")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionAttemptDecision:
    kind: WorkbenchRagEvalQuestionAttemptDecisionKind
    reason: str


class WorkbenchRagEvalQuestionAttemptDecisionPolicy:
    def decide(
        self, command: DecideWorkbenchRagEvalQuestionAttemptCommand
    ) -> WorkbenchRagEvalQuestionAttemptDecision:
        if command.error_kind == "minute_limit":
            return _decision(
                WorkbenchRagEvalQuestionAttemptDecisionKind.WAIT_CAPACITY_WINDOW,
                command.error_kind,
            )
        has_next_route = command.current_route_index + 1 < command.route_count
        if command.error_kind == "request_too_large":
            compatible = (
                has_next_route
                and command.next_route_input_limit is not None
                and command.input_tokens <= command.next_route_input_limit
            )
            return _decision(
                WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_LARGER_INPUT_ROUTE
                if compatible
                else WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL,
                command.error_kind,
            )
        retryable = command.error_kind in {
            "invalid_json",
            "invalid_contract",
            "auth_error",
            "daily_limit",
        }
        if not retryable:
            return _decision(
                WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL, command.error_kind
            )
        if (
            command.same_route_attempt_number < command.same_route_retry_limit
            and command.error_kind != "daily_limit"
        ):
            return _decision(
                WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_SAME_ROUTE,
                command.error_kind,
            )
        if has_next_route:
            return _decision(
                WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_FALLBACK_ROUTE,
                command.error_kind,
            )
        return _decision(
            WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL, command.error_kind
        )


def _decision(
    kind: WorkbenchRagEvalQuestionAttemptDecisionKind, reason: str
) -> WorkbenchRagEvalQuestionAttemptDecision:
    return WorkbenchRagEvalQuestionAttemptDecision(kind=kind, reason=reason)
