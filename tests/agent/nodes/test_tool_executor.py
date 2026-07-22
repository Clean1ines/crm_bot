from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.runtime.tool_execution import (
    ToolExecutionOutcome,
    ToolExecutionStatus,
)

import pytest

from src.agent.nodes.tool_executor import create_tool_executor_node


@pytest.mark.asyncio
async def test_tool_executor_returns_failed_tool_response_when_tool_missing():
    node = create_tool_executor_node(tool_registry=MagicMock())

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"project_id": "project-1"})

    assert result["requires_human"] is False
    assert result["tool_result"] is None
    assert result["tool_execution_status"] == "failed"
    assert result["tool_execution_safe_error_code"] == "missing_tool_selection"
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"


@pytest.mark.asyncio
async def test_tool_executor_returns_tool_result_on_success():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"ok": True, "value": 1})
    )
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "tool_name": "crm.create",
                "tool_args": {"name": "Alice"},
                "project_id": "project-1",
                "thread_id": "thread-1",
            }
        )

    assert result == {
        "tool_result": {"ok": True, "value": 1},
        "requires_human": False,
        "tool_execution_status": "succeeded",
        "generation_mode": "TOOL_RESULT_RESPONSE",
    }
    tool_registry.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_executor_success_flows_to_tool_result_generation_without_kb_fallback():
    from types import SimpleNamespace
    import json

    from src.agent.nodes.response_generator import create_response_generator_node

    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(
            payload={"ok": True, "text": "created record"}
        )
    )
    tool_node = create_tool_executor_node(tool_registry=tool_registry)

    response_llm = MagicMock()
    response_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "answerability": "supported",
                    "answer": "Tool result: created record.",
                    "supporting_entry_ids": [],
                    "unsupported_aspects": [],
                }
            )
        )
    )
    response_node = create_response_generator_node(
        llm=response_llm, model_name="test-model"
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "decision": "CALL_TOOL",
        "tool_name": "crm.create",
        "tool_args": {"name": "Alice"},
        "project_id": "project-1",
        "thread_id": "thread-1",
        "user_input": "?????? ??????",
        "history": [],
        "knowledge_chunks": [],
        "knowledge_retrieval_status": "skipped",
        "project_configuration": {"settings": {"target_language": "en"}},
    }

    with (
        patch(
            "src.agent.nodes.tool_executor.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
    ):
        state.update(await tool_node(state))
        result = await response_node(state)

    assert state["tool_result"] == {"ok": True, "text": "created record"}
    assert result["response_text"] == "Tool result: created record."
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["metadata"]["retrieval_status"] == "skipped"
    assert result["evidence_reference_status"] == "not_applicable"
    assert result["semantic_grounding_status"] == "unchecked"
    response_llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"ok": False, "value": "business data"},
        {"error": "business validation message"},
        ["list payload"],
        "scalar payload",
    ],
)
async def test_tool_executor_treats_typed_success_payload_as_success(payload):
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome(
            status=ToolExecutionStatus.SUCCEEDED,
            payload=payload,
        )
    )
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "tool_name": "crm.lookup",
                "tool_args": {},
                "project_id": "project-",
                "thread_id": "thread-",
            }
        )

    assert result["tool_execution_status"] == "succeeded"
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["requires_human"] is False
    assert result["tool_result"] == payload


@pytest.mark.asyncio
async def test_tool_executor_failed_outcome_sets_tool_generation_mode():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome(
            status=ToolExecutionStatus.FAILED,
            safe_error_code="tool_down",
        )
    )
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "tool_name": "crm.lookup",
                "tool_args": {},
                "project_id": "project-",
                "thread_id": "thread-",
            }
        )

    assert result["tool_execution_status"] == "failed"
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["requires_human"] is False
    assert result["tool_result"] is None
    assert result["tool_execution_safe_error_code"] == "tool_execution_failed"


@pytest.mark.asyncio
async def test_tool_executor_exception_policy_is_failed_not_handoff():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(side_effect=RuntimeError("boom"))
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "tool_name": "crm.lookup",
                "tool_args": {},
                "project_id": "project-",
                "thread_id": "thread-",
            }
        )

    assert result["tool_execution_status"] == "failed"
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["requires_human"] is False
    assert result["tool_execution_safe_error_code"] == "tool_execution_failed"


@pytest.mark.asyncio
async def test_tool_executor_requires_human_outcome_does_not_set_generation_mode():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(
        return_value=ToolExecutionOutcome(
            status=ToolExecutionStatus.REQUIRES_HUMAN,
            response_text="Manual help needed",
        )
    )
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "tool_name": "crm.lookup",
                "tool_args": {},
                "project_id": "project-",
                "thread_id": "thread-",
            }
        )

    assert result["tool_execution_status"] == "requires_human"
    assert result["requires_human"] is True
    assert "generation_mode" not in result
    assert result["response_text"] == "Manual help needed"


@pytest.mark.asyncio
async def test_tool_executor_rejects_raw_registry_return_as_invalid_outcome():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"value": 1})
    node = create_tool_executor_node(tool_registry=tool_registry)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.tool_executor.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "tool_name": "crm.lookup",
                "tool_args": {},
                "project_id": "project-",
                "thread_id": "thread-",
            }
        )

    assert result["tool_execution_status"] == "failed"
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["tool_execution_safe_error_code"] == "invalid_tool_outcome"
