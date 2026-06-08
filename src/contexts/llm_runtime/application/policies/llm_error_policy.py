from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


class LlmErrorDispositionKind(StrEnum):
    RETRY_SAME_ROUTE = "retry_same_route"
    DEFER_UNTIL = "defer_until"
    TRY_ALTERNATE_ROUTE = "try_alternate_route"
    VALIDATION_RETRY = "validation_retry"
    CONFIRM_EMPTY_OUTPUT = "confirm_empty_output"
    TERMINAL_FAILURE = "terminal_failure"


@dataclass(frozen=True, slots=True)
class LlmErrorDisposition:
    kind: LlmErrorDispositionKind
    error_kind: LlmErrorKind
    wait_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is LlmErrorDispositionKind.DEFER_UNTIL:
            if self.wait_until is None:
                raise ValueError("DEFER_UNTIL disposition must have wait_until")
            if self.wait_until.tzinfo is None or self.wait_until.utcoffset() is None:
                raise ValueError("wait_until must be timezone-aware")
        if (
            self.kind is not LlmErrorDispositionKind.DEFER_UNTIL
            and self.wait_until is not None
        ):
            raise ValueError("Only DEFER_UNTIL disposition may carry wait_until")


class LlmErrorPolicy:
    """Maps typed LLM failure kinds to provider-neutral handling decisions."""

    def decide(
        self,
        error_kind: LlmErrorKind,
        *,
        wait_until: datetime | None = None,
    ) -> LlmErrorDisposition:
        if error_kind is LlmErrorKind.MINUTE_LIMIT:
            return LlmErrorDisposition(
                kind=LlmErrorDispositionKind.DEFER_UNTIL,
                error_kind=error_kind,
                wait_until=wait_until,
            )

        if error_kind in {
            LlmErrorKind.REQUEST_TOO_LARGE,
            LlmErrorKind.OUTPUT_TOO_LARGE,
            LlmErrorKind.DAILY_LIMIT,
        }:
            return LlmErrorDisposition(
                kind=LlmErrorDispositionKind.TRY_ALTERNATE_ROUTE,
                error_kind=error_kind,
            )

        if error_kind in {
            LlmErrorKind.INVALID_OUTPUT,
            LlmErrorKind.VALIDATION_FAILED,
        }:
            return LlmErrorDisposition(
                kind=LlmErrorDispositionKind.VALIDATION_RETRY,
                error_kind=error_kind,
            )

        if error_kind is LlmErrorKind.EMPTY_OUTPUT:
            return LlmErrorDisposition(
                kind=LlmErrorDispositionKind.CONFIRM_EMPTY_OUTPUT,
                error_kind=error_kind,
            )

        if error_kind is LlmErrorKind.AUTH_ERROR:
            return LlmErrorDisposition(
                kind=LlmErrorDispositionKind.TERMINAL_FAILURE,
                error_kind=error_kind,
            )

        return LlmErrorDisposition(
            kind=LlmErrorDispositionKind.RETRY_SAME_ROUTE,
            error_kind=error_kind,
        )
