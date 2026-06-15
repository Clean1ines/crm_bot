from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import pytest
from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
)
from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
    LlmProviderMessage,
    LlmProviderMessageRole,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderResult,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.application.ports.llm_task_unit_of_work_port import (
    LlmTaskEvent,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.application.use_cases.execute_and_record_llm_task import (
    ExecuteAndRecordLlmTask,
    ExecuteAndRecordLlmTaskCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmTaskFailed,
    LlmTaskSucceeded,
)
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
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


@dataclass(frozen=True, slots=True)
class FakeProvider:
    result: LlmProviderResult

    def invoke(
        self, *, task: LlmTask, route: LlmRoute, provider_input: LlmProviderInput
    ) -> LlmProviderResult:
        assert task.status is LlmTaskStatus.RUNNING
        assert task.selected_route == route
        assert provider_input.messages
        return self.result


@dataclass(slots=True)
class FakeLlmTaskUnitOfWork:
    committed: bool = False
    rolled_back: bool = False
    saved_tasks: list[LlmTask] = field(default_factory=list)
    saved_attempts: list[LlmAttempt] = field(default_factory=list)
    appended_events: list[LlmTaskEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
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


def _route(model: str = "model-1", account: str = "account-1") -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId(model),
        account_ref=ProviderAccountRef(account),
    )


def _candidate(
    *,
    model: str = "model-1",
    account: str = "account-1",
    context_window_tokens: int = 8000,
    max_output_tokens: int = 2000,
    model_rank: int = 0,
    account_rank: int = 0,
) -> LlmRouteCandidate:
    return LlmRouteCandidate(
        route=_route(model, account),
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        model_rank=model_rank,
        account_rank=account_rank,
    )


def _task() -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=OutputContractRef("contract-1"),
    )


def _provider_input() -> LlmProviderInput:
    return LlmProviderInput(
        messages=(
            LlmProviderMessage(
                role=LlmProviderMessageRole.USER, content="Return JSON."
            ),
        )
    )


def _command(
    candidates: tuple[LlmRouteCandidate, ...] | None = None,
) -> ExecuteAndRecordLlmTaskCommand:
    return ExecuteAndRecordLlmTaskCommand(
        task=_task(),
        route=_route(),
        candidates=candidates or (_candidate(),),
        provider_input=_provider_input(),
        attempt_id="attempt-1",
        attempt_number=1,
        started_at=_now(),
        finished_at=_now() + timedelta(seconds=1),
        occurred_at=_now() + timedelta(seconds=1),
    )


def test_execute_and_record_success_commits_task_attempt_and_success_event() -> None:
    unit_of_work = FakeLlmTaskUnitOfWork()
    use_case = ExecuteAndRecordLlmTask(
        provider=FakeProvider(
            LlmProviderSuccess(
                raw_text='{"ok": true}',
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            )
        ),
        unit_of_work=unit_of_work,
    )
    outcome = use_case.execute(_command())
    assert outcome.kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
    assert unit_of_work.saved_tasks[0].status is LlmTaskStatus.SUCCEEDED
    assert unit_of_work.saved_attempts[0].usage == TokenUsage(
        input_tokens=10, output_tokens=5
    )
    assert isinstance(unit_of_work.appended_events[0], LlmTaskSucceeded)
    assert unit_of_work.actions == [
        "save_task",
        "save_attempt",
        "append_event",
        "commit",
    ]


def test_execute_and_record_route_change_commits_retryable_task_and_failed_event() -> (
    None
):
    current = _candidate(
        model="model-1", account="account-1", context_window_tokens=8000, model_rank=0
    )
    larger = _candidate(
        model="model-2", account="account-1", context_window_tokens=32000, model_rank=1
    )
    unit_of_work = FakeLlmTaskUnitOfWork()
    use_case = ExecuteAndRecordLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.REQUEST_TOO_LARGE)
        ),
        unit_of_work=unit_of_work,
    )
    outcome = use_case.execute(_command(candidates=(current, larger)))
    assert outcome.kind is ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED
    assert outcome.route == larger.route
    assert unit_of_work.saved_tasks[0].status is LlmTaskStatus.RETRYABLE_FAILED
    assert unit_of_work.saved_attempts[0].error_kind is LlmErrorKind.REQUEST_TOO_LARGE
    assert isinstance(unit_of_work.appended_events[0], LlmTaskFailed)


def test_execute_and_record_rolls_back_when_recording_fails() -> None:
    unit_of_work = FakeLlmTaskUnitOfWork(fail_on_commit=True)
    use_case = ExecuteAndRecordLlmTask(
        provider=FakeProvider(LlmProviderSuccess(raw_text="ok")),
        unit_of_work=unit_of_work,
    )
    with pytest.raises(RuntimeError, match="commit failed"):
        use_case.execute(_command())
    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_task",
        "save_attempt",
        "append_event",
        "commit",
        "rollback",
    ]


def test_execute_and_record_command_requires_timestamps() -> None:
    with pytest.raises(ValueError):
        ExecuteAndRecordLlmTaskCommand(
            task=_task(),
            route=_route(),
            candidates=(_candidate(),),
            provider_input=_provider_input(),
            attempt_id="attempt-1",
            attempt_number=1,
            started_at=datetime(2026, 6, 8, 12, 0),
            finished_at=_now(),
            occurred_at=_now(),
        )
    with pytest.raises(ValueError):
        ExecuteAndRecordLlmTaskCommand(
            task=_task(),
            route=_route(),
            candidates=(_candidate(),),
            provider_input=_provider_input(),
            attempt_id="attempt-1",
            attempt_number=1,
            started_at=_now(),
            finished_at=_now() - timedelta(seconds=1),
            occurred_at=_now(),
        )
