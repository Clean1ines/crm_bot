from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


class ExecuteLlmTaskOutcomeKind(StrEnum):
    SUCCEEDED = "succeeded"
    ROUTE_CHANGE_REQUIRED = "route_change_required"
    DEFERRED = "deferred"
    RETRY_REQUIRED = "retry_required"
    SPLIT_REQUIRED = "split_required"
    DAILY_EXHAUSTED = "daily_exhausted"
    CONFIRM_EMPTY_OUTPUT_REQUIRED = "confirm_empty_output_required"
    TERMINAL_FAILED = "terminal_failed"


@dataclass(frozen=True, slots=True)
class ExecuteLlmTaskOutcome:
    kind: ExecuteLlmTaskOutcomeKind
    task: LlmTask
    raw_text: str | None = None
    usage: TokenUsage | None = None
    route: LlmRoute | None = None
    wait_until: datetime | None = None
    error_kind: LlmErrorKind | None = None

    def __post_init__(self) -> None:
        if self.kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED:
            if self.raw_text is None:
                raise ValueError("SUCCEEDED outcome must carry raw_text")
            if self.error_kind is not None:
                raise ValueError("SUCCEEDED outcome must not carry error_kind")
        else:
            if self.raw_text is not None:
                raise ValueError("Only SUCCEEDED outcome may carry raw_text")

        if self.kind is ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED:
            if self.route is None:
                raise ValueError("ROUTE_CHANGE_REQUIRED outcome must carry route")
        elif self.route is not None:
            raise ValueError("Only ROUTE_CHANGE_REQUIRED outcome may carry route")

        if self.kind is ExecuteLlmTaskOutcomeKind.DEFERRED:
            if self.wait_until is None:
                raise ValueError("DEFERRED outcome must carry wait_until")
            if self.wait_until.tzinfo is None or self.wait_until.utcoffset() is None:
                raise ValueError("wait_until must be timezone-aware")
        elif self.wait_until is not None:
            raise ValueError("Only DEFERRED outcome may carry wait_until")

        if (
            self.kind is not ExecuteLlmTaskOutcomeKind.SUCCEEDED
            and self.error_kind is None
        ):
            raise ValueError("Non-success outcome must carry error_kind")
