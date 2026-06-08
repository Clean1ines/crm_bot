from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.application.ports.llm_task_unit_of_work_port import (
    LlmTaskEvent,
)
from src.contexts.llm_runtime.application.use_cases.record_llm_task_execution import (
    RecordLlmTaskExecution,
    RecordLlmTaskExecutionCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskSucceeded
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


@dataclass(slots=True)
class FakeLlmTaskUnitOfWork:
    saved_tasks: list[LlmTask] = field(default_factory=list)
    saved_attempts: list[LlmAttempt] = field(default_factory=list)
    appended_events: list[LlmTaskEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    fail_on_commit: bool = False

    def save_task(self, task: LlmTask) -> None:
        self.actions.append("save_task")
        self.saved_tasks.append(task)

    def save_attempt(self, attempt: LlmAttempt) -> None:
        self.actions.append("save_attempt")
        self.saved_attempts.append(attempt)

    def append_event(self, event: LlmTaskEvent) -> None:
        self.actions.append("append_event")
        self.appended_events.append(event)

    def commit(self) -> None:
        self.actions.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId("model-1"),
        account_ref=ProviderAccountRef("account-1"),
    )


def _task() -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=OutputContractRef("contract-1"),
    )


def _attempt() -> LlmAttempt:
    return LlmAttempt(
        attempt_id="attempt-1",
        task_id="task-1",
        attempt_number=1,
        route=_route(),
        started_at=_now(),
        finished_at=_now() + timedelta(seconds=1),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def test_record_llm_task_execution_commits_task_attempt_and_events_atomically() -> None:
    unit_of_work = FakeLlmTaskUnitOfWork()
    task = _task()
    attempt = _attempt()
    event = LlmTaskSucceeded(task_id=task.task_id, occurred_at=_now())

    RecordLlmTaskExecution(unit_of_work=unit_of_work).execute(
        RecordLlmTaskExecutionCommand(
            task=task,
            attempt=attempt,
            events=(event,),
        ),
    )

    assert unit_of_work.saved_tasks == [task]
    assert unit_of_work.saved_attempts == [attempt]
    assert unit_of_work.appended_events == [event]
    assert unit_of_work.actions == [
        "save_task",
        "save_attempt",
        "append_event",
        "commit",
    ]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back


def test_record_llm_task_execution_can_commit_task_without_attempt_or_events() -> None:
    unit_of_work = FakeLlmTaskUnitOfWork()
    task = _task()

    RecordLlmTaskExecution(unit_of_work=unit_of_work).execute(
        RecordLlmTaskExecutionCommand(task=task),
    )

    assert unit_of_work.saved_tasks == [task]
    assert unit_of_work.saved_attempts == []
    assert unit_of_work.appended_events == []
    assert unit_of_work.actions == ["save_task", "commit"]
    assert unit_of_work.committed


def test_record_llm_task_execution_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeLlmTaskUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        RecordLlmTaskExecution(unit_of_work=unit_of_work).execute(
            RecordLlmTaskExecutionCommand(
                task=_task(),
                attempt=_attempt(),
            ),
        )

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_task",
        "save_attempt",
        "commit",
        "rollback",
    ]
