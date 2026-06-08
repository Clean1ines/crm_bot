from __future__ import annotations

from dataclasses import dataclass
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
from src.contexts.llm_runtime.application.ports.llm_output_validation_port import (
    LlmOutputValidationFailure,
    LlmOutputValidationResult,
    LlmOutputValidationSuccess,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderResult,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.application.use_cases.execute_llm_task import (
    ExecuteLlmTask,
    ExecuteLlmTaskCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
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
        self,
        *,
        task: LlmTask,
        route: LlmRoute,
        provider_input: LlmProviderInput,
    ) -> LlmProviderResult:
        assert task.status is LlmTaskStatus.RUNNING
        assert task.selected_route == route
        assert provider_input.messages
        return self.result


@dataclass(frozen=True, slots=True)
class FakeOutputValidator:
    result: LlmOutputValidationResult

    def validate(self, *, task: LlmTask, raw_text: str) -> LlmOutputValidationResult:
        assert task.status is LlmTaskStatus.RUNNING
        assert raw_text
        return self.result


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
    model: str,
    account: str,
    context_window_tokens: int = 8_000,
    max_output_tokens: int = 2_000,
    model_rank: int = 0,
    account_rank: int = 0,
    minute_capacity_available: bool = True,
    daily_capacity_available: bool = True,
    unavailable_until: datetime | None = None,
) -> LlmRouteCandidate:
    return LlmRouteCandidate(
        route=_route(model, account),
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        model_rank=model_rank,
        account_rank=account_rank,
        minute_capacity_available=minute_capacity_available,
        daily_capacity_available=daily_capacity_available,
        unavailable_until=unavailable_until,
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
                role=LlmProviderMessageRole.USER,
                content="Return JSON.",
            ),
        ),
    )


def _command(
    candidates: tuple[LlmRouteCandidate, ...] | None = None,
) -> ExecuteLlmTaskCommand:
    route = _route()
    default_candidates = (_candidate(model="model-1", account="account-1"),)
    return ExecuteLlmTaskCommand(
        task=_task(),
        route=route,
        candidates=candidates or default_candidates,
        provider_input=_provider_input(),
    )


def test_execute_llm_task_success_returns_succeeded_outcome() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderSuccess(
                raw_text='{"ok": true}',
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            ),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED
    assert outcome.task.status is LlmTaskStatus.SUCCEEDED
    assert outcome.raw_text == '{"ok": true}'
    assert outcome.usage == TokenUsage(input_tokens=10, output_tokens=5)


def test_execute_llm_task_validates_provider_success_before_accepting_it() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderSuccess(
                raw_text='{"ok": true}',
                usage=TokenUsage(input_tokens=10, output_tokens=5),
            ),
        ),
        output_validator=FakeOutputValidator(LlmOutputValidationSuccess()),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED
    assert outcome.task.status is LlmTaskStatus.SUCCEEDED


def test_validation_failure_turns_provider_success_into_retry_required() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderSuccess(raw_text='{"broken": true}'),
        ),
        output_validator=FakeOutputValidator(
            LlmOutputValidationFailure(
                error_kind=LlmErrorKind.VALIDATION_FAILED,
                error_codes=("missing_required_field",),
            ),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED
    assert outcome.task.status is LlmTaskStatus.RETRYABLE_FAILED
    assert outcome.error_kind is LlmErrorKind.VALIDATION_FAILED
    assert outcome.raw_text is None


def test_empty_output_validation_requires_confirmation() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderSuccess(raw_text="{}"),
        ),
        output_validator=FakeOutputValidator(
            LlmOutputValidationFailure(
                error_kind=LlmErrorKind.EMPTY_OUTPUT,
                error_codes=("empty_output",),
            ),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.CONFIRM_EMPTY_OUTPUT_REQUIRED
    assert outcome.task.status is LlmTaskStatus.RETRYABLE_FAILED
    assert outcome.error_kind is LlmErrorKind.EMPTY_OUTPUT


def test_request_too_large_returns_route_change_when_larger_context_route_exists() -> (
    None
):
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        model_rank=0,
    )
    larger = _candidate(
        model="model-2",
        account="account-1",
        context_window_tokens=32_000,
        model_rank=1,
    )

    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.REQUEST_TOO_LARGE),
        ),
    )

    outcome = use_case.execute(
        ExecuteLlmTaskCommand(
            task=_task(),
            route=current.route,
            candidates=(current, larger),
            provider_input=_provider_input(),
        ),
    )

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED
    assert outcome.route == larger.route
    assert outcome.task.status is LlmTaskStatus.RETRYABLE_FAILED


def test_request_too_large_returns_split_required_when_no_larger_route_exists() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.REQUEST_TOO_LARGE),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.SPLIT_REQUIRED
    assert outcome.task.status is LlmTaskStatus.TERMINAL_FAILED


def test_minute_limit_uses_other_account_when_available() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        minute_capacity_available=False,
        unavailable_until=_now() + timedelta(seconds=60),
    )
    other_account = _candidate(
        model="model-1",
        account="account-2",
        account_rank=1,
    )

    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.MINUTE_LIMIT),
        ),
    )

    outcome = use_case.execute(
        ExecuteLlmTaskCommand(
            task=_task(),
            route=current.route,
            candidates=(current, other_account),
            provider_input=_provider_input(),
        ),
    )

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED
    assert outcome.route == other_account.route


def test_minute_limit_defers_when_no_account_available() -> None:
    wait_until = _now() + timedelta(seconds=60)
    current = _candidate(
        model="model-1",
        account="account-1",
        minute_capacity_available=False,
        unavailable_until=wait_until,
    )

    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(
                error_kind=LlmErrorKind.MINUTE_LIMIT, wait_until=wait_until
            ),
        ),
    )

    outcome = use_case.execute(
        ExecuteLlmTaskCommand(
            task=_task(),
            route=current.route,
            candidates=(current,),
            provider_input=_provider_input(),
        ),
    )

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.DEFERRED
    assert outcome.wait_until == wait_until
    assert outcome.task.status is LlmTaskStatus.DEFERRED


def test_daily_limit_exhaustion_is_visible_outcome() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        daily_capacity_available=False,
    )

    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.DAILY_LIMIT),
        ),
    )

    outcome = use_case.execute(
        ExecuteLlmTaskCommand(
            task=_task(),
            route=current.route,
            candidates=(current,),
            provider_input=_provider_input(),
        ),
    )

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.DAILY_EXHAUSTED
    assert outcome.task.status is LlmTaskStatus.RETRYABLE_FAILED


def test_empty_output_requires_confirmation_outcome() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.EMPTY_OUTPUT),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.CONFIRM_EMPTY_OUTPUT_REQUIRED
    assert outcome.task.status is LlmTaskStatus.RETRYABLE_FAILED


def test_validation_failure_returns_retry_required() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.VALIDATION_FAILED),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED
    assert outcome.task.status is LlmTaskStatus.RETRYABLE_FAILED


def test_auth_error_returns_terminal_failed() -> None:
    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderFailure(error_kind=LlmErrorKind.AUTH_ERROR),
        ),
    )

    outcome = use_case.execute(_command())

    assert outcome.kind is ExecuteLlmTaskOutcomeKind.TERMINAL_FAILED
    assert outcome.task.status is LlmTaskStatus.TERMINAL_FAILED


def test_execute_llm_task_rejects_task_that_cannot_start() -> None:
    succeeded = LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=OutputContractRef("contract-1"),
        status=LlmTaskStatus.SUCCEEDED,
    )

    use_case = ExecuteLlmTask(
        provider=FakeProvider(
            LlmProviderSuccess(raw_text="ok"),
        ),
    )

    with pytest.raises(ValueError):
        use_case.execute(
            ExecuteLlmTaskCommand(
                task=succeeded,
                route=_route(),
                candidates=(_candidate(model="model-1", account="account-1"),),
                provider_input=_provider_input(),
            ),
        )
