from __future__ import annotations

from enum import StrEnum


class EmbeddingTaskStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"

    @property
    def is_terminal(self) -> bool:
        return self in {
            EmbeddingTaskStatus.SUCCEEDED,
            EmbeddingTaskStatus.TERMINAL_FAILED,
        }
