from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.dto.runtime_dto import GraphExecutionRequestDto, ProjectRuntimeContextDto
from src.application.orchestration.graph_factory import GraphFactory, GraphExecutor


def make_factory():
    with patch("src.application.orchestration.graph_factory.create_default_agent", return_value=MagicMock()):
        return GraphFactory(
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


def test_build_agent_state_uses_explicit_runtime_context():
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

    assert state["project_id"] == "project-id"
    assert state["thread_id"] == "thread-id"
    assert state["chat_id"] == 123
    assert state["user_input"] == "hello"
    assert state["history"] == [{"role": "user", "content": "old"}]
    assert state["trace_id"] == "trace-id"
    assert state["project_configuration"]["settings"]["brand_name"] == "Brand"


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

    assert result.response_text == "Sorry, I couldn't generate a response."


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
