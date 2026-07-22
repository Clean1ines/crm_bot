from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.escalate import create_escalate_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.domain.runtime.tool_execution import ToolExecutionOutcome


@pytest.mark.asyncio
async def test_escalate_returns_fallback_when_thread_id_missing():
    node = create_escalate_node(
        thread_lifecycle_repo=MagicMock(),
        queue_repo=MagicMock(),
        ticket_create_tool=MagicMock(),
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.escalate.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node({"project_id": "project-1"})

    assert result["requires_human"] is True
    assert result["tool_result"] is None


@pytest.mark.asyncio
async def test_escalate_creates_ticket_and_enqueues_notifications():
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"ticket_id": "ticket-123"})
    )
    node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.escalate.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "client_profile": {"id": "client-1"},
            }
        )

    assert result["requires_human"] is True
    assert result["ticket_created"] is True
    assert result["escalation_failed"] is False
    assert result["handoff_completed"] is True
    assert result["thread_waiting_manager"] is True
    assert result["notification_degraded"] is False
    assert result["handoff_ticket_id"] == "ticket-123"
    assert "technical_ticket_id" not in result
    thread_lifecycle_repo.update_status.assert_awaited_once()
    assert queue_repo.enqueue.await_count == 2
    ticket_create_tool.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_escalate_records_partial_failure_when_waiting_manager_update_fails():
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock(side_effect=RuntimeError("db down"))
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"ticket_id": "ticket-123"})
    )
    node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.escalate.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.escalate.logger") as logger_mock,
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "previous_lifecycle": "active_client",
                "lifecycle": "handoff_to_manager",
                "client_profile": {"id": "client-1"},
                "dialog_state": {
                    "lifecycle": "handoff_to_manager",
                    "lead_status": "handoff_to_manager",
                    "handoff_confirmation_pending": True,
                    "last_cta": "call_manager",
                },
            }
        )

    assert result["requires_human"] is False
    assert result["escalation_failed"] is True
    assert result["ticket_created"] is True
    assert result["handoff_completed"] is False
    assert result["thread_waiting_manager"] is False
    assert result["handoff_ticket_id"] == "ticket-123"
    assert "technical_ticket_id" not in result
    assert result["decision"] == "RESPOND"
    assert result["lifecycle"] == "active_client"
    assert result["tool_execution_safe_error_code"] == "handoff_state_transition_failed"
    assert not any(
        call.args and call.args[0] == "Manager handoff completed"
        for call in logger_mock.info.call_args_list
    )
    thread_lifecycle_repo.update_status.assert_awaited_once()
    queue_repo.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_escalate_marks_notification_degraded_after_waiting_manager_success():
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock(
        side_effect=[RuntimeError("queue down"), "metrics-1"]
    )
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"ticket_id": "ticket-123"})
    )
    node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.escalate.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.escalate.logger") as logger_mock,
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "client_profile": {"id": "client-1"},
            }
        )

    assert result["requires_human"] is True
    assert result["escalation_failed"] is False
    assert result["ticket_created"] is True
    assert result["handoff_completed"] is True
    assert result["thread_waiting_manager"] is True
    assert result["notification_degraded"] is True
    assert result["handoff_ticket_id"] == "ticket-123"
    assert "technical_ticket_id" not in result
    assert any(
        call.args
        and call.args[0] == "Manager notification failed; handoff remains active"
        for call in logger_mock.exception.call_args_list
    )
    assert any(
        call.args and call.args[0] == "Manager handoff completed"
        for call in logger_mock.info.call_args_list
    )
    thread_lifecycle_repo.update_status.assert_awaited_once()
    assert queue_repo.enqueue.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        ToolExecutionOutcome.succeeded(payload=None),
        ToolExecutionOutcome.succeeded(payload={}),
        ToolExecutionOutcome.succeeded(payload={"ticket_id": None}),
        ToolExecutionOutcome.succeeded(payload={"ticket_id": ""}),
        ToolExecutionOutcome.succeeded(payload="unexpected"),
    ],
)
async def test_escalate_aborts_malformed_successful_ticket_creation(caplog, outcome):
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(return_value=outcome)
    node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.escalate.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "client_profile": {"id": "client-1"},
                "decision": "ESCALATE",
                "lifecycle": "handoff_to_manager",
                "previous_lifecycle": "active_client",
                "cta": "call_manager",
                "resolved_cta": "call_manager",
                "resolved_cta_reply": "affirmative",
                "dialog_state": {
                    "lifecycle": "handoff_to_manager",
                    "lead_status": "handoff_to_manager",
                    "handoff_confirmation_pending": True,
                    "last_cta": "call_manager",
                },
            }
        )

    assert result["requires_human"] is False
    assert result["escalation_failed"] is True
    assert result["ticket_created"] is False
    assert result["handoff_ticket_id"] is None
    assert result["handoff_completed"] is False
    assert result["thread_waiting_manager"] is False
    assert result["notification_degraded"] is False
    assert result["decision"] == "RESPOND"
    assert result["lifecycle"] == "active_client"
    assert result["cta"] == "none"
    assert result["resolved_cta"] is None
    assert result["resolved_cta_reply"] is None
    assert result["tool_execution_status"] == "failed"
    assert result["tool_execution_safe_error_code"] == "invalid_tool_outcome"
    assert result["dialog_state"]["lifecycle"] == "active_client"
    assert result["dialog_state"]["handoff_confirmation_pending"] is False
    assert result["dialog_state"]["last_cta"] is None
    assert "Ticket created" not in caplog.text
    thread_lifecycle_repo.update_status.assert_not_awaited()
    queue_repo.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_escalate_aborts_when_ticket_creation_fails(caplog):
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(
        return_value=ToolExecutionOutcome.failed(
            safe_error_code="ticket_creation_failed"
        )
    )
    node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.escalate.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "client_profile": {"id": "client-1"},
            }
        )

    assert result["requires_human"] is False
    assert result["escalation_failed"] is True
    assert result["ticket_created"] is False
    assert result["handoff_ticket_id"] is None
    assert result["handoff_completed"] is False
    assert result["thread_waiting_manager"] is False
    assert result["notification_degraded"] is False
    assert result["decision"] == "RESPOND"
    assert result["tool_execution_status"] == "failed"
    assert result["tool_execution_safe_error_code"] == "ticket_creation_failed"
    assert "Ticket created" not in caplog.text
    thread_lifecycle_repo.update_status.assert_not_awaited()
    queue_repo.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_escalate_aborts_when_ticket_creation_raises(caplog):
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(side_effect=RuntimeError("db down"))
    node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.escalate.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": "need help",
                "client_profile": {"id": "client-1"},
            }
        )

    assert result["requires_human"] is False
    assert result["escalation_failed"] is True
    assert result["ticket_created"] is False
    assert result["handoff_ticket_id"] is None
    assert result["handoff_completed"] is False
    assert result["thread_waiting_manager"] is False
    assert result["notification_degraded"] is False
    assert result["decision"] == "RESPOND"
    assert result["tool_execution_status"] == "failed"
    assert result["tool_execution_safe_error_code"] == "ticket_creation_failed"
    assert "Ticket created" not in caplog.text
    assert "db down" not in result["response_text"]
    thread_lifecycle_repo.update_status.assert_not_awaited()
    queue_repo.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_to_escalate_failed_ticket_restores_assistant_state():
    policy_node = create_policy_engine_node(event_repo=None)
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    ticket_create_tool = MagicMock()
    ticket_create_tool.run = AsyncMock(
        return_value=ToolExecutionOutcome.failed(
            safe_error_code="ticket_creation_failed"
        )
    )
    escalate_node = create_escalate_node(
        thread_lifecycle_repo=thread_lifecycle_repo,
        queue_repo=queue_repo,
        ticket_create_tool=ticket_create_tool,
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "thread_id": "thread-1",
        "project_id": "project-1",
        "user_input": "Да",
        "lifecycle": "active_client",
        "resolved_cta": "call_manager",
        "resolved_cta_reply": "affirmative",
        "turn_relation": "continuation",
        "dialog_state": {
            "last_intent": "product",
            "last_topic": "product",
            "last_cta": "call_manager",
            "repeat_count": 0,
            "lead_status": "active_client",
            "lifecycle": "active_client",
            "handoff_confirmation_pending": False,
        },
    }

    with (
        patch(
            "src.agent.nodes.policy_engine.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch(
            "src.agent.nodes.escalate.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
    ):
        policy_patch = await policy_node(state)
        state.update(policy_patch)
        assert state["decision"] == "ESCALATE"
        assert state["requires_human"] is True

        escalation_patch = await escalate_node(state)
        state.update(escalation_patch)

        assert state["requires_human"] is False
        assert state["escalation_failed"] is True
        assert state["ticket_created"] is False
        assert state["handoff_completed"] is False
        assert state["thread_waiting_manager"] is False
        assert state["decision"] == "RESPOND"
        assert state.get("lifecycle") != "handoff_to_manager"
        assert state.get("cta") == "none"
        assert state.get("resolved_cta") is None
        assert state.get("resolved_cta_reply") is None
        assert state["dialog_state"]["handoff_confirmation_pending"] is False
        thread_lifecycle_repo.update_status.assert_not_awaited()
        queue_repo.enqueue.assert_not_awaited()

        next_policy_patch = await policy_node(
            {
                **state,
                "user_input": "Что умеет Axole?",
                "response_text": None,
                "intent": "other",
                "topic": "product",
                "turn_relation": "new_topic",
                "is_repeat_like": False,
                "should_search_kb": True,
                "should_generate_answer": True,
            }
        )

    assert next_policy_patch["decision"] == "LLM_GENERATE"
    assert next_policy_patch.get("requires_human") is not True
    assert next_policy_patch["generation_mode"] == "KNOWLEDGE_ANSWER"
    assert next_policy_patch.get("ticket_created") is None
