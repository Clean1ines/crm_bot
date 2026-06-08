from __future__ import annotations

from enum import StrEnum


class LlmTaskStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEFERRED = "deferred"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            LlmTaskStatus.SUCCEEDED,
            LlmTaskStatus.TERMINAL_FAILED,
            LlmTaskStatus.CANCELLED,
        }
