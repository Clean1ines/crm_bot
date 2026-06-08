from __future__ import annotations

from typing import Protocol, TypeAlias

from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmDailyLimitExhausted,
    LlmMinuteLimitHit,
    LlmTaskDeferred,
    LlmTaskFailed,
    LlmTaskSucceeded,
)


LlmTaskEvent: TypeAlias = (
    LlmTaskSucceeded
    | LlmTaskDeferred
    | LlmTaskFailed
    | LlmMinuteLimitHit
    | LlmDailyLimitExhausted
)


class LlmTaskUnitOfWorkPort(Protocol):
    """Transaction boundary for committing LLM task execution consequences."""

    def save_task(self, task: LlmTask) -> None:
        """Persist the current task state."""

    def save_attempt(self, attempt: LlmAttempt) -> None:
        """Persist an execution attempt."""

    def append_event(self, event: LlmTaskEvent) -> None:
        """Append an event that must be committed with task state."""

    def commit(self) -> None:
        """Commit all staged changes atomically."""

    def rollback(self) -> None:
        """Rollback staged changes after failure."""
