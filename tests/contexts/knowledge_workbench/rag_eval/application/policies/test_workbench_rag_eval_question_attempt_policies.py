from datetime import datetime, timezone

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_attempt_decision_policy import (
    DecideWorkbenchRagEvalQuestionAttemptCommand,
    WorkbenchRagEvalQuestionAttemptDecisionKind,
    WorkbenchRagEvalQuestionAttemptDecisionPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_attempt_next_action_policy import (
    WorkbenchRagEvalQuestionAttemptNextActionPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation import (
    WorkbenchRagEvalQuestionGenerationOutputValidator,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionStatus,
)


def _decide(**overrides: object):
    values = dict(
        error_kind="invalid_contract",
        same_route_attempt_number=1,
        same_route_retry_limit=2,
        current_route_index=0,
        route_count=2,
        input_tokens=100,
        next_route_input_limit=1000,
    )
    values.update(overrides)
    return WorkbenchRagEvalQuestionAttemptDecisionPolicy().decide(
        DecideWorkbenchRagEvalQuestionAttemptCommand(**values)
    )  # type: ignore[arg-type]


def test_invalid_json_retries_same_route_before_budget_exhaustion() -> None:
    action = WorkbenchRagEvalQuestionAttemptNextActionPolicy().decide_next_action(
        _decide(error_kind="invalid_json")
    )
    assert action.retry_plan is WorkItemRetryPlan.RETRY_SAME_ROUTE
    assert action.terminal is False


def test_exhausted_same_route_uses_automatic_fallback() -> None:
    action = WorkbenchRagEvalQuestionAttemptNextActionPolicy().decide_next_action(
        _decide(same_route_attempt_number=2)
    )
    assert action.retry_plan is WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE


def test_exhausted_all_routes_is_terminal() -> None:
    decision = _decide(same_route_attempt_number=2, current_route_index=1)
    assert decision.kind is WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL
    assert (
        WorkbenchRagEvalQuestionAttemptNextActionPolicy()
        .decide_next_action(decision)
        .terminal
        is True
    )


def test_minute_capacity_waits_without_model_fallback() -> None:
    action = WorkbenchRagEvalQuestionAttemptNextActionPolicy().decide_next_action(
        _decide(error_kind="minute_limit")
    )
    assert action.retry_plan is WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW


def test_auth_error_is_bounded_by_same_route_budget() -> None:
    assert (
        _decide(error_kind="auth_error").kind
        is WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_SAME_ROUTE
    )
    assert (
        _decide(error_kind="auth_error", same_route_attempt_number=2).kind
        is WorkbenchRagEvalQuestionAttemptDecisionKind.RETRY_FALLBACK_ROUTE
    )


def test_request_too_large_falls_back_only_to_compatible_profile() -> None:
    compatible = WorkbenchRagEvalQuestionAttemptNextActionPolicy().decide_next_action(
        _decide(
            error_kind="request_too_large",
            input_tokens=900,
            next_route_input_limit=1000,
        )
    )
    incompatible = _decide(
        error_kind="request_too_large", input_tokens=1100, next_route_input_limit=1000
    )
    assert compatible.retry_plan is WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE
    assert incompatible.kind is WorkbenchRagEvalQuestionAttemptDecisionKind.TERMINAL


def test_invalid_qgen_contract_is_persisted_as_retryable_with_retry_plan() -> None:
    result = WorkbenchRagEvalQuestionGenerationOutputValidator(
        WorkbenchRagEvalQuestionGenerator.from_prompt_file()
    ).validate(
        dispatch_payload={
            "schedule_payload": {"possible_questions": []},
            "llm_allocation": {"model_ref": "qwen/qwen3-32b"},
        },
        output_payload={"raw_text": "not-json"},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=datetime.now(timezone.utc),
        attempt_number=1,
    )
    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.metadata["retry_plan"] == WorkItemRetryPlan.RETRY_SAME_ROUTE.value
