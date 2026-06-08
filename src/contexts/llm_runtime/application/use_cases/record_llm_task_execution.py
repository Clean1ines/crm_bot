from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.application.ports.llm_task_unit_of_work_port import (
    LlmTaskEvent,
    LlmTaskUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask


@dataclass(frozen=True, slots=True)
class RecordLlmTaskExecutionCommand:
    task: LlmTask
    attempt: LlmAttempt | None = None
    events: tuple[LlmTaskEvent, ...] = ()


class RecordLlmTaskExecution:
    """Commit LLM task execution consequences through a Unit of Work.

    This use case deliberately does not know the concrete database, queue,
    provider adapter, or caller business process. It only defines what the LLM
    Runtime needs to persist atomically at this boundary.
    """

    def __init__(self, *, unit_of_work: LlmTaskUnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, command: RecordLlmTaskExecutionCommand) -> None:
        try:
            self._unit_of_work.save_task(command.task)

            if command.attempt is not None:
                self._unit_of_work.save_attempt(command.attempt)

            for event in command.events:
                self._unit_of_work.append_event(event)

            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise
