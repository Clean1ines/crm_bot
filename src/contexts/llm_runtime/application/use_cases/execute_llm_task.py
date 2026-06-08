from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.application.policies.llm_error_policy import (
    LlmErrorDispositionKind,
    LlmErrorPolicy,
)
from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
    LlmRoutePlanDecisionKind,
    LlmRoutePlanningPolicy,
)
from src.contexts.llm_runtime.application.ports.llm_output_validation_port import (
    LlmOutputValidationPort,
    LlmOutputValidationResult,
    LlmOutputValidationSuccess,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderPort,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcome,
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.state_machines.llm_task_state_machine import (
    LlmTaskStateMachine,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


@dataclass(frozen=True, slots=True)
class ExecuteLlmTaskCommand:
    task: LlmTask
    route: LlmRoute
    candidates: tuple[LlmRouteCandidate, ...]


class ExecuteLlmTask:
    """Application use case for one provider-neutral task execution attempt.

    This use case does not persist state. It returns a typed outcome for the
    caller to commit through a later transaction boundary.
    """

    def __init__(
        self,
        *,
        provider: LlmProviderPort,
        output_validator: LlmOutputValidationPort | None = None,
        error_policy: LlmErrorPolicy | None = None,
        route_planning_policy: LlmRoutePlanningPolicy | None = None,
    ) -> None:
        self._provider = provider
        self._output_validator = output_validator or _AcceptAllOutputValidator()
        self._error_policy = error_policy or LlmErrorPolicy()
        self._route_planning_policy = route_planning_policy or LlmRoutePlanningPolicy()

    def execute(self, command: ExecuteLlmTaskCommand) -> ExecuteLlmTaskOutcome:
        running_task = LlmTaskStateMachine.start_ready(
            command.task,
            route=command.route,
        )

        result = self._provider.invoke(
            task=running_task,
            route=command.route,
        )

        if isinstance(result, LlmProviderSuccess):
            validation_result = self._output_validator.validate(
                task=running_task,
                raw_text=result.raw_text,
            )

            if isinstance(validation_result, LlmOutputValidationSuccess):
                succeeded_task = LlmTaskStateMachine.succeed_running(running_task)
                return ExecuteLlmTaskOutcome(
                    kind=ExecuteLlmTaskOutcomeKind.SUCCEEDED,
                    task=succeeded_task,
                    raw_text=result.raw_text,
                    usage=result.usage,
                )

            return self._handle_failure(
                running_task=running_task,
                failure=LlmProviderFailure(error_kind=validation_result.error_kind),
                current_route=command.route,
                candidates=command.candidates,
            )

        return self._handle_failure(
            running_task=running_task,
            failure=result,
            current_route=command.route,
            candidates=command.candidates,
        )

    def _handle_failure(
        self,
        *,
        running_task: LlmTask,
        failure: LlmProviderFailure,
        current_route: LlmRoute,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> ExecuteLlmTaskOutcome:
        if failure.error_kind in {
            LlmErrorKind.REQUEST_TOO_LARGE,
            LlmErrorKind.OUTPUT_TOO_LARGE,
            LlmErrorKind.MINUTE_LIMIT,
            LlmErrorKind.DAILY_LIMIT,
        }:
            return self._handle_route_relevant_failure(
                running_task=running_task,
                failure=failure,
                current_route=current_route,
                candidates=candidates,
            )

        disposition = self._error_policy.decide(
            failure.error_kind,
            wait_until=failure.wait_until,
        )

        if disposition.kind is LlmErrorDispositionKind.DEFER_UNTIL:
            wait_until = disposition.wait_until
            if wait_until is None:
                raise ValueError("DEFER_UNTIL disposition must carry wait_until")

            deferred_task = LlmTaskStateMachine.defer_running(
                running_task,
                wait_until=wait_until,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.DEFERRED,
                task=deferred_task,
                wait_until=wait_until,
                error_kind=failure.error_kind,
            )

        if disposition.kind is LlmErrorDispositionKind.CONFIRM_EMPTY_OUTPUT:
            retryable_task = LlmTaskStateMachine.fail_running_retryable(
                running_task,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.CONFIRM_EMPTY_OUTPUT_REQUIRED,
                task=retryable_task,
                error_kind=failure.error_kind,
            )

        if disposition.kind is LlmErrorDispositionKind.TERMINAL_FAILURE:
            terminal_task = LlmTaskStateMachine.fail_running_terminal(
                running_task,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.TERMINAL_FAILED,
                task=terminal_task,
                error_kind=failure.error_kind,
            )

        retryable_task = LlmTaskStateMachine.fail_running_retryable(
            running_task,
            error_kind=failure.error_kind,
        )
        return ExecuteLlmTaskOutcome(
            kind=ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED,
            task=retryable_task,
            error_kind=failure.error_kind,
        )

    def _handle_route_relevant_failure(
        self,
        *,
        running_task: LlmTask,
        failure: LlmProviderFailure,
        current_route: LlmRoute,
        candidates: tuple[LlmRouteCandidate, ...],
    ) -> ExecuteLlmTaskOutcome:
        decision = self._route_planning_policy.decide(
            failure.error_kind,
            current_route=current_route,
            candidates=candidates,
        )

        if decision.kind is LlmRoutePlanDecisionKind.USE_ROUTE:
            retryable_task = LlmTaskStateMachine.fail_running_retryable(
                running_task,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED,
                task=retryable_task,
                route=decision.route,
                error_kind=failure.error_kind,
            )

        if decision.kind is LlmRoutePlanDecisionKind.WAIT_UNTIL:
            wait_until = decision.wait_until
            if wait_until is None:
                raise ValueError("WAIT_UNTIL route decision must carry wait_until")

            deferred_task = LlmTaskStateMachine.defer_running(
                running_task,
                wait_until=wait_until,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.DEFERRED,
                task=deferred_task,
                wait_until=wait_until,
                error_kind=failure.error_kind,
            )

        if decision.kind is LlmRoutePlanDecisionKind.SPLIT_REQUIRED:
            terminal_task = LlmTaskStateMachine.fail_running_terminal(
                running_task,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.SPLIT_REQUIRED,
                task=terminal_task,
                error_kind=failure.error_kind,
            )

        if decision.kind is LlmRoutePlanDecisionKind.DAILY_EXHAUSTED:
            retryable_task = LlmTaskStateMachine.fail_running_retryable(
                running_task,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.DAILY_EXHAUSTED,
                task=retryable_task,
                error_kind=failure.error_kind,
            )

        if decision.kind is LlmRoutePlanDecisionKind.TERMINAL_FAILURE:
            terminal_task = LlmTaskStateMachine.fail_running_terminal(
                running_task,
                error_kind=failure.error_kind,
            )
            return ExecuteLlmTaskOutcome(
                kind=ExecuteLlmTaskOutcomeKind.TERMINAL_FAILED,
                task=terminal_task,
                error_kind=failure.error_kind,
            )

        retryable_task = LlmTaskStateMachine.fail_running_retryable(
            running_task,
            error_kind=failure.error_kind,
        )
        return ExecuteLlmTaskOutcome(
            kind=ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED,
            task=retryable_task,
            error_kind=failure.error_kind,
        )


class _AcceptAllOutputValidator:
    def validate(self, *, task: LlmTask, raw_text: str) -> LlmOutputValidationResult:
        return LlmOutputValidationSuccess()
