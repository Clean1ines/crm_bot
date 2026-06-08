from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


@dataclass(frozen=True, slots=True)
class LlmTaskDomainEvent:
    task_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class LlmTaskSucceeded(LlmTaskDomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class LlmTaskDeferred(LlmTaskDomainEvent):
    wait_until: datetime
    error_kind: LlmErrorKind


@dataclass(frozen=True, slots=True)
class LlmTaskFailed(LlmTaskDomainEvent):
    error_kind: LlmErrorKind


@dataclass(frozen=True, slots=True)
class LlmMinuteLimitHit(LlmTaskDomainEvent):
    wait_until: datetime


@dataclass(frozen=True, slots=True)
class LlmDailyLimitExhausted(LlmTaskDomainEvent):
    error_kind: LlmErrorKind = LlmErrorKind.DAILY_LIMIT
