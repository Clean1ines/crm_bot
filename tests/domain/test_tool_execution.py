from src.domain.runtime.tool_execution import (
    ToolSafeErrorCode,
    ToolExecutionContext,
    ToolExecutionOutcome,
    ToolExecutionResult,
    ToolExecutionStatus,
    normalize_tool_execution_status,
)


def test_tool_execution_context_builds_registry_context():
    context = ToolExecutionContext.from_state(
        {
            "tool_name": "crm.create",
            "tool_args": {"name": "Alice"},
            "project_id": "project-1",
            "thread_id": "thread-1",
        }
    )

    assert context.execution_context() == {
        "project_id": "project-1",
        "thread_id": "thread-1",
    }
    assert context.tool_args == {"name": "Alice"}


def test_tool_execution_result_serializes_optional_response_text():
    result = ToolExecutionResult(
        tool_result=None, requires_human=True, response_text="failed"
    )

    assert result.to_state_patch() == {
        "tool_result": None,
        "requires_human": True,
        "response_text": "failed",
    }


def test_tool_execution_result_serializes_status_and_safe_code():
    result = ToolExecutionResult(
        tool_result=None,
        requires_human=False,
        status=ToolExecutionStatus.FAILED,
        safe_error_code="tool_down",
    )

    assert result.to_state_patch() == {
        "tool_result": None,
        "requires_human": False,
        "tool_execution_status": "failed",
        "tool_execution_safe_error_code": "tool_execution_failed",
    }


def test_tool_execution_result_serializes_tool_response_text():
    result = ToolExecutionResult(
        tool_result=None,
        requires_human=False,
        status=ToolExecutionStatus.SUCCEEDED,
        tool_response_text="Done.",
    )

    assert result.to_state_patch() == {
        "tool_result": None,
        "requires_human": False,
        "tool_execution_status": "succeeded",
        "tool_response_text": "Done.",
    }


def test_tool_execution_outcome_constructors_are_explicit():
    success = ToolExecutionOutcome.succeeded(
        payload={"ok": False, "value": "business data"}
    )
    failed = ToolExecutionOutcome.failed(safe_error_code="tool_business_rejected")
    requires_human = ToolExecutionOutcome.requires_human(response_text="Manual")

    assert success.status is ToolExecutionStatus.SUCCEEDED
    assert success.payload == {"ok": False, "value": "business data"}
    assert failed.status is ToolExecutionStatus.FAILED
    assert failed.safe_error_code == "tool_business_rejected"
    assert requires_human.status is ToolExecutionStatus.REQUIRES_HUMAN
    assert requires_human.response_text == "Manual"
    assert requires_human.safe_error_code == "manual_action_required"


def test_tool_execution_outcome_rejects_success_with_safe_error_code():
    import pytest

    with pytest.raises(ValueError):
        ToolExecutionOutcome(
            status=ToolExecutionStatus.SUCCEEDED,
            safe_error_code=ToolSafeErrorCode.TOOL_EXECUTION_FAILED.value,
        )


def test_tool_execution_outcome_normalizes_non_success_missing_safe_error_code():
    failed = ToolExecutionOutcome(status=ToolExecutionStatus.FAILED)
    requires_human = ToolExecutionOutcome(status=ToolExecutionStatus.REQUIRES_HUMAN)

    assert failed.safe_error_code == "tool_execution_failed"
    assert requires_human.safe_error_code == "manual_action_required"


def test_tool_execution_outcome_normalizes_unknown_safe_error_code():
    failed = ToolExecutionOutcome(
        status=ToolExecutionStatus.FAILED,
        safe_error_code="vendor_specific_exception",
    )

    assert failed.safe_error_code == "tool_execution_failed"


def test_normalize_tool_execution_status_accepts_known_values_only():
    assert normalize_tool_execution_status("Succeeded") is ToolExecutionStatus.SUCCEEDED
    assert normalize_tool_execution_status("failed") is ToolExecutionStatus.FAILED
    assert (
        normalize_tool_execution_status("requires_human")
        is ToolExecutionStatus.REQUIRES_HUMAN
    )
    assert normalize_tool_execution_status("unknown") is None
