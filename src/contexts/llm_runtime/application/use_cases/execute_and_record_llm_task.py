from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.llm_runtime.application.policies.llm_execution_recording_policy import (
    LlmAttemptRecordingInput,
    LlmExecutionRecordingPolicy,
)
from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import LlmProviderPort
from src.contexts.llm_runtime.application.ports.llm_task_unit_of_work_port import (
    LlmTaskUnitOfWorkPort,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcome,
)
from src.contexts.llm_runtime.application.use_cases.execute_llm_task import (
    ExecuteLlmTask,
    ExecuteLlmTaskCommand,
)
from src.contexts.llm_runtime.application.use_cases.record_llm_task_execution import (
    RecordLlmTaskExecution,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


@dataclass(frozen=True, slots=True)
class ExecuteAndRecordLlmTaskCommand:
    task: LlmTask
    route: LlmRoute
    candidates: tuple[LlmRouteCandidate, ...]
    attempt_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.attempt_id or not self.attempt_id.strip():
            raise ValueError("attempt_id must be non-empty")
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be >= 1")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
            raise ValueError("finished_at must be timezone-aware")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")


class ExecuteAndRecordLlmTask:
    """Runs one LLM task attempt and records its consequences through a boundary."""

    def __init__(
        self,
        *,
        provider: LlmProviderPort,
        unit_of_work: LlmTaskUnitOfWorkPort,
        execute_task: ExecuteLlmTask | None = None,
        recording_policy: LlmExecutionRecordingPolicy | None = None,
        recorder: RecordLlmTaskExecution | None = None,
    ) -> None:
        self._execute_task = execute_task or ExecuteLlmTask(provider=provider)
        self._recording_policy = recording_policy or LlmExecutionRecordingPolicy()
        self._recorder = recorder or RecordLlmTaskExecution(unit_of_work=unit_of_work)

    def execute(self, command: ExecuteAndRecordLlmTaskCommand) -> ExecuteLlmTaskOutcome:
        outcome = self._execute_task.execute(
            ExecuteLlmTaskCommand(
                task=command.task,
                route=command.route,
                candidates=command.candidates,
            ),
        )

        record_command = self._recording_policy.build_record_command(
            outcome=outcome,
            attempt_input=LlmAttemptRecordingInput(
                attempt_id=command.attempt_id,
                attempt_number=command.attempt_number,
                route=command.route,
                started_at=command.started_at,
                finished_at=command.finished_at,
            ),
            occurred_at=command.occurred_at,
        )

        self._recorder.execute(record_command)

        return outcome
