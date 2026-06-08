from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcome,
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.application.use_cases.record_llm_task_execution import (
    RecordLlmTaskExecutionCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmDailyLimitExhausted,
    LlmMinuteLimitHit,
    LlmTaskDeferred,
    LlmTaskFailed,
    LlmTaskSucceeded,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


@dataclass(frozen=True, slots=True)
class LlmAttemptRecordingInput:
    attempt_id: str
    attempt_number: int
    route: LlmRoute
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        if not self.attempt_id or not self.attempt_id.strip():
            raise ValueError("attempt_id must be non-empty")
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be >= 1")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
            raise ValueError("finished_at must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")


class LlmExecutionRecordingPolicy:
    """Builds persistence command for an execution outcome.

    This policy does not persist anything itself. It maps an application outcome
    into task state, optional attempt record, and domain events that should later
    be committed through the Unit of Work boundary.
    """

    def build_record_command(
        self,
        *,
        outcome: ExecuteLlmTaskOutcome,
        attempt_input: LlmAttemptRecordingInput,
        occurred_at: datetime,
    ) -> RecordLlmTaskExecutionCommand:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")

        attempt = LlmAttempt(
            attempt_id=attempt_input.attempt_id,
            task_id=outcome.task.task_id,
            attempt_number=attempt_input.attempt_number,
            route=attempt_input.route,
            started_at=attempt_input.started_at,
            finished_at=attempt_input.finished_at,
            usage=outcome.usage,
            error_kind=outcome.error_kind,
        )

        event = self._event_for_outcome(
            outcome=outcome,
            occurred_at=occurred_at,
        )

        return RecordLlmTaskExecutionCommand(
            task=outcome.task,
            attempt=attempt,
            events=(event,),
        )

    def _event_for_outcome(
        self,
        *,
        outcome: ExecuteLlmTaskOutcome,
        occurred_at: datetime,
    ) -> (
        LlmTaskSucceeded
        | LlmTaskDeferred
        | LlmTaskFailed
        | LlmMinuteLimitHit
        | LlmDailyLimitExhausted
    ):
        if outcome.kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED:
            return LlmTaskSucceeded(
                task_id=outcome.task.task_id,
                occurred_at=occurred_at,
            )

        error_kind = outcome.error_kind
        if error_kind is None:
            raise ValueError("Non-success outcome must carry error_kind")

        if outcome.kind is ExecuteLlmTaskOutcomeKind.DEFERRED:
            wait_until = outcome.wait_until
            if wait_until is None:
                raise ValueError("DEFERRED outcome must carry wait_until")

            if error_kind is LlmErrorKind.MINUTE_LIMIT:
                return LlmMinuteLimitHit(
                    task_id=outcome.task.task_id,
                    occurred_at=occurred_at,
                    wait_until=wait_until,
                )

            return LlmTaskDeferred(
                task_id=outcome.task.task_id,
                occurred_at=occurred_at,
                wait_until=wait_until,
                error_kind=error_kind,
            )

        if outcome.kind is ExecuteLlmTaskOutcomeKind.DAILY_EXHAUSTED:
            return LlmDailyLimitExhausted(
                task_id=outcome.task.task_id,
                occurred_at=occurred_at,
            )

        return LlmTaskFailed(
            task_id=outcome.task.task_id,
            occurred_at=occurred_at,
            error_kind=error_kind,
        )
