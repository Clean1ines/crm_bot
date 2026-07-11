from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_output_validation_policy import (
    WorkbenchRagEvalQuestionOutputValidationOutcome,
    WorkbenchRagEvalQuestionOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)


def test_invalid_json_has_typed_validation_outcome_without_retry_routing() -> None:
    policy = WorkbenchRagEvalQuestionOutputValidationPolicy(
        WorkbenchRagEvalQuestionGenerator.from_prompt_file(),
    )
    result = policy.validate(
        raw_text="not-json",
        existing_possible_questions=(),
    )
    assert (
        result.outcome is WorkbenchRagEvalQuestionOutputValidationOutcome.INVALID_JSON
    )
    assert result.questions == ()
    assert result.error is not None


def test_validation_policy_source_has_no_route_or_fake_token_logic() -> None:
    import inspect

    source = inspect.getsource(WorkbenchRagEvalQuestionOutputValidationPolicy)
    assert "route_catalog" not in source
    assert "model_refs" not in source
    assert "input_tokens" not in source
    assert "retry_plan" not in source
    assert "WorkItemRetryPlan" not in source
    assert "attempt_number" not in source
    assert "invalid_output_retry_limit" not in source
