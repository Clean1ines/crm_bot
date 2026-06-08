from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus


class InvalidLlmTaskTransition(ValueError):
    """Raised when an LlmTask lifecycle transition violates the state machine."""


class LlmTaskStateMachine:
    @staticmethod
    def start_ready(task: LlmTask, *, route: LlmRoute) -> LlmTask:
        if task.status not in {
            LlmTaskStatus.READY,
            LlmTaskStatus.DEFERRED,
            LlmTaskStatus.RETRYABLE_FAILED,
        }:
            raise InvalidLlmTaskTransition(
                f"Cannot start task from status {task.status}"
            )

        return replace(
            task,
            status=LlmTaskStatus.RUNNING,
            attempt_count=task.attempt_count + 1,
            selected_route=route,
            wait_until=None,
            last_error_kind=None,
        )

    @staticmethod
    def succeed_running(task: LlmTask) -> LlmTask:
        LlmTaskStateMachine._require_running(task, "succeed")
        return replace(
            task,
            status=LlmTaskStatus.SUCCEEDED,
            wait_until=None,
            last_error_kind=None,
        )

    @staticmethod
    def defer_running(
        task: LlmTask,
        *,
        wait_until: datetime,
        error_kind: LlmErrorKind,
    ) -> LlmTask:
        LlmTaskStateMachine._require_running(task, "defer")
        if wait_until.tzinfo is None or wait_until.utcoffset() is None:
            raise ValueError("wait_until must be timezone-aware")
        return replace(
            task,
            status=LlmTaskStatus.DEFERRED,
            wait_until=wait_until,
            last_error_kind=error_kind,
        )

    @staticmethod
    def fail_running_retryable(task: LlmTask, *, error_kind: LlmErrorKind) -> LlmTask:
        LlmTaskStateMachine._require_running(task, "mark retryable failed")
        return replace(
            task,
            status=LlmTaskStatus.RETRYABLE_FAILED,
            wait_until=None,
            last_error_kind=error_kind,
        )

    @staticmethod
    def fail_running_terminal(task: LlmTask, *, error_kind: LlmErrorKind) -> LlmTask:
        LlmTaskStateMachine._require_running(task, "mark terminal failed")
        return replace(
            task,
            status=LlmTaskStatus.TERMINAL_FAILED,
            wait_until=None,
            last_error_kind=error_kind,
        )

    @staticmethod
    def cancel(task: LlmTask, *, error_kind: LlmErrorKind | None = None) -> LlmTask:
        if task.status.is_terminal:
            raise InvalidLlmTaskTransition(
                f"Cannot cancel terminal task from status {task.status}"
            )
        return replace(
            task,
            status=LlmTaskStatus.CANCELLED,
            wait_until=None,
            last_error_kind=error_kind,
        )

    @staticmethod
    def _require_running(task: LlmTask, action: str) -> None:
        if task.status is not LlmTaskStatus.RUNNING:
            raise InvalidLlmTaskTransition(
                f"Cannot {action} task from status {task.status}"
            )
