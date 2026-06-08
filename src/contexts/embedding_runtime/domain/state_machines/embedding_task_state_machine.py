from __future__ import annotations

from dataclasses import replace

from src.contexts.embedding_runtime.domain.entities.embedding_task import EmbeddingTask
from src.contexts.embedding_runtime.domain.value_objects.embedding_task_status import (
    EmbeddingTaskStatus,
)


class InvalidEmbeddingTaskTransition(ValueError):
    """Raised when an embedding task lifecycle transition is invalid."""


class EmbeddingTaskStateMachine:
    @staticmethod
    def start_ready(task: EmbeddingTask) -> EmbeddingTask:
        if task.status is not EmbeddingTaskStatus.READY:
            raise InvalidEmbeddingTaskTransition(
                f"Cannot start embedding task from status {task.status}"
            )
        return replace(
            task,
            status=EmbeddingTaskStatus.RUNNING,
            last_error_kind=None,
        )

    @staticmethod
    def succeed_running(task: EmbeddingTask) -> EmbeddingTask:
        EmbeddingTaskStateMachine._require_running(task, "succeed")
        return replace(
            task,
            status=EmbeddingTaskStatus.SUCCEEDED,
            last_error_kind=None,
        )

    @staticmethod
    def fail_running_retryable(
        task: EmbeddingTask,
        *,
        error_kind: str,
    ) -> EmbeddingTask:
        EmbeddingTaskStateMachine._require_running(task, "mark retryable failed")
        EmbeddingTaskStateMachine._validate_error_kind(error_kind)
        return replace(
            task,
            status=EmbeddingTaskStatus.RETRYABLE_FAILED,
            last_error_kind=error_kind,
        )

    @staticmethod
    def fail_running_terminal(
        task: EmbeddingTask,
        *,
        error_kind: str,
    ) -> EmbeddingTask:
        EmbeddingTaskStateMachine._require_running(task, "mark terminal failed")
        EmbeddingTaskStateMachine._validate_error_kind(error_kind)
        return replace(
            task,
            status=EmbeddingTaskStatus.TERMINAL_FAILED,
            last_error_kind=error_kind,
        )

    @staticmethod
    def reset_retryable_to_ready(task: EmbeddingTask) -> EmbeddingTask:
        if task.status is not EmbeddingTaskStatus.RETRYABLE_FAILED:
            raise InvalidEmbeddingTaskTransition(
                f"Cannot reset embedding task from status {task.status}"
            )
        return replace(
            task,
            status=EmbeddingTaskStatus.READY,
            last_error_kind=None,
        )

    @staticmethod
    def _require_running(task: EmbeddingTask, action: str) -> None:
        if task.status is not EmbeddingTaskStatus.RUNNING:
            raise InvalidEmbeddingTaskTransition(
                f"Cannot {action} embedding task from status {task.status}"
            )

    @staticmethod
    def _validate_error_kind(error_kind: str) -> None:
        if not error_kind or not error_kind.strip():
            raise ValueError("error_kind must be non-empty")
