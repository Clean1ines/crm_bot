from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.responder import create_responder_node


@pytest.mark.asyncio
async def test_responder_returns_human_fallback_when_chat_id_missing():
    node = create_responder_node(tool_registry=MagicMock(), thread_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.responder.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"response_text": "hello"})

    assert result["requires_human"] is True
    assert result["message_sent"] is False


@pytest.mark.asyncio
async def test_responder_sends_message_and_saves_assistant_copy():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"ok": True})
    thread_repo = MagicMock()
    thread_repo.add_message = AsyncMock()
    node = create_responder_node(tool_registry=tool_registry, thread_repo=thread_repo)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch("src.agent.nodes.responder.log_node_execution", AsyncMock(side_effect=passthrough)):
        result = await node({"chat_id": 123, "thread_id": "thread-1", "project_id": "project-1", "response_text": "ok"})

    assert result == {"message_sent": True, "response_text": None}
    tool_registry.execute.assert_awaited_once()
    thread_repo.add_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_responder_delivery_success_degrades_when_assistant_copy_fails():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(return_value={"ok": True})
    thread_repo = MagicMock()
    thread_repo.add_message = AsyncMock(side_effect=RuntimeError("db write failed"))
    node = create_responder_node(tool_registry=tool_registry, thread_repo=thread_repo)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch("src.agent.nodes.responder.log_node_execution", AsyncMock(side_effect=passthrough)),
        patch("src.agent.nodes.responder.logger") as logger,
    ):
        result = await node({
            "chat_id": 123,
            "thread_id": "thread-1",
            "project_id": "project-1",
            "response_text": "ok",
        })

    assert result == {"message_sent": True, "response_text": None}
    logger.exception.assert_called_once()
    assert logger.exception.call_args.kwargs["extra"]["policy"] == "delivery_success_degrade_persistence"


@pytest.mark.asyncio
async def test_responder_send_exception_returns_requires_human_fallback():
    tool_registry = MagicMock()
    tool_registry.execute = AsyncMock(side_effect=RuntimeError("telegram down"))
    node = create_responder_node(tool_registry=tool_registry, thread_repo=None)

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch("src.agent.nodes.responder.log_node_execution", AsyncMock(side_effect=passthrough)),
        patch("src.agent.nodes.responder.logger") as logger,
    ):
        result = await node({
            "chat_id": 123,
            "thread_id": "thread-1",
            "project_id": "project-1",
            "response_text": "ok",
        })

    assert result["message_sent"] is False
    assert result["requires_human"] is True
    logger.exception.assert_called_once()
    assert logger.exception.call_args.kwargs["extra"]["policy"] == "fallback_requires_human"
