from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.dto.runtime_dto import GraphExecutionRequestDto, ProjectRuntimeContextDto
from src.application.orchestration.graph_factory import (
    GRAPH_EMPTY_RESPONSE_FALLBACK_TEXT,
    GraphExecutor,
    GraphFactory,
)


def make_factory():
    return GraphFactory(
        agent_factory=MagicMock(return_value=MagicMock()),
        tool_registry=MagicMock(),
        thread_repo=MagicMock(),
        queue_repo=MagicMock(),
        event_repo=MagicMock(),
        project_repo=MagicMock(),
        memory_repo=MagicMock(),
        logger=MagicMock(),
    )


def make_executor():
    executor = GraphExecutor(logger=MagicMock())
    executor.RECENT_MESSAGES_LIMIT = 3
    return executor


def test_trim_recent_history_respects_limit():
    executor = make_executor()
    history = [{"content": str(i)} for i in range(5)]

    assert executor.trim_recent_history(history) == [
        {"content": "2"},
        {"content": "3"},
        {"content": "4"},
    ]


def test_build_agent_state_uses_explicit_runtime_context_and_full_contract_defaults():
    executor = make_executor()
    request = GraphExecutionRequestDto(
        project_id="project-id",
        thread_id="thread-id",
        chat_id=123,
        question="hello",
        recent_history=[{"role": "user", "content": "old"}],
        runtime_context=ProjectRuntimeContextDto.from_record({"settings": {"brand_name": "Brand"}}),
        trace_id="trace-id",
    )

    state = executor.build_agent_state(request=request)

    assert state["messages"] == []
    assert state["project_id"] == "project-id"
    assert state["thread_id"] == "thread-id"
    assert state["chat_id"] == 123
    assert state["user_input"] == "hello"
    assert state["history"] == [{"role": "user", "content": "old"}]
    assert state["trace_id"] == "trace-id"
    assert state["project_configuration"]["settings"]["brand_name"] == "Brand"

    assert state["escalation_requested"] is False
    assert state["tool_calls"] is None
    assert state["client_profile"] is None
    assert state["conversation_summary"] == ""
    assert state["knowledge_chunks"] is None
    assert state["decision"] is None
    assert state["tool_name"] is None
    assert state["tool_args"] is None
    assert state["tool_result"] is None
    assert state["user_memory"] is None
    assert state["response_text"] is None
    assert state["requires_human"] is False
    assert state["confidence"] is None
    assert state["message_sent"] is False
    assert state["client_id"] is None
    assert state["close_ticket"] is False
    assert state["intent"] is None
    assert state["cta"] is None
    assert state["lifecycle"] is None
    assert state["features"] is None
    assert state["dialog_state"] is None
    assert state["topic"] is None
    assert state["lead_status"] is None
    assert state["repeat_count"] is None


def test_extract_graph_result_handles_pre_sent_messages():
    executor = make_executor()

    result = executor.extract_graph_result(
        {"message_sent": True},
        question="hello",
        thread_id="thread-id",
    )

    assert result.delivered is True
    assert result.response_text == ""


def test_extract_graph_result_falls_back_when_graph_returns_no_text():
    executor = make_executor()

    result = executor.extract_graph_result({}, question="hello", thread_id="thread-id")

    assert result.response_text == GRAPH_EMPTY_RESPONSE_FALLBACK_TEXT


@pytest.mark.asyncio
async def test_invoke_graph_returns_outcome_from_graph_result():
    executor = make_executor()
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(return_value={"response_text": "answer", "delivered": False})

    request = GraphExecutionRequestDto(
        project_id="project-id",
        thread_id="thread-id",
        chat_id=123,
        question="hello",
        recent_history=[],
        runtime_context=ProjectRuntimeContextDto(),
        trace_id="trace-id",
    )

    outcome = await executor.invoke_graph(graph=graph, request=request)

    assert outcome.text == "answer"
    assert outcome.delivered is False


def test_graph_factory_returns_default_agent_for_empty_graph_json():
    factory = make_factory()

    assert factory.build_graph_from_json({}) is factory.agent


def test_graph_factory_returns_default_agent_for_invalid_json():
    factory = make_factory()

    assert factory.build_graph_from_json("{not json") is factory.agent


@pytest.mark.asyncio
async def test_graph_factory_returns_default_agent_for_project():
    factory = make_factory()

    assert await factory.get_graph_for_project("project-id") is factory.agent
