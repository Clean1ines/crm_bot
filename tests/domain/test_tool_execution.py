from src.domain.runtime.tool_execution import ToolExecutionContext, ToolExecutionResult


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
    result = ToolExecutionResult(tool_result=None, requires_human=True, response_text="failed")

    assert result.to_state_patch() == {
        "tool_result": None,
        "requires_human": True,
        "response_text": "failed",
    }
