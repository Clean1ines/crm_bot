from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


@dataclass(frozen=True, slots=True)
class LlmAttempt:
    attempt_id: str
    task_id: str
    attempt_number: int
    route: LlmRoute
    started_at: datetime
    finished_at: datetime | None = None
    usage: TokenUsage | None = None
    error_kind: LlmErrorKind | None = None

    def __post_init__(self) -> None:
        if not self.attempt_id or not self.attempt_id.strip():
            raise ValueError("LlmAttempt.attempt_id must be non-empty")
        if not self.task_id or not self.task_id.strip():
            raise ValueError("LlmAttempt.task_id must be non-empty")
        if self.attempt_number < 1:
            raise ValueError("LlmAttempt.attempt_number must be >= 1")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at is not None:
            if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
                raise ValueError("finished_at must be timezone-aware")
            if self.finished_at < self.started_at:
                raise ValueError("finished_at must be >= started_at")
