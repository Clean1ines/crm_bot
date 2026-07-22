from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.load_state import create_load_state_node
from src.domain.project_plane.memory_views import MemoryEntryView
from src.domain.runtime.persistence import PersistenceContext


@pytest.mark.asyncio
async def test_load_state_node_uses_thread_runtime_snapshots():
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
            "chat_id": 123,
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(
        return_value=SimpleNamespace(
            to_record=lambda: {
                "intent": "pricing",
                "lifecycle": "warm",
                "cta": None,
                "decision": "RESPOND",
            }
        )
    )
    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(
        return_value=[{"role": "user", "content": "hello"}]
    )
    thread_runtime_state_repo.get_state_json = AsyncMock(return_value={"ignored": True})

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=None,
    )

    result = await node({"thread_id": "thread-1", "project_id": "project-1"})

    assert result["conversation_summary"] == "summary"
    assert result["client_id"] == "client-1"
    assert result["history"] == [{"role": "user", "content": "hello"}]
    assert result["intent"] == "pricing"
    assert result["lifecycle"] == "warm"
    assert result["decision"] == "RESPOND"
    assert result["user_memory"] == {}


@pytest.mark.asyncio
async def test_load_state_degrades_to_empty_user_memory_when_memory_repo_fails():
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
            "chat_id": 123,
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(return_value=None)
    thread_runtime_state_repo.get_state_json = AsyncMock(return_value={})

    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])

    memory_repo = MagicMock()
    memory_repo.get_for_user_view = AsyncMock(
        side_effect=RuntimeError("memory unavailable")
    )

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=memory_repo,
    )

    with patch("src.agent.nodes.load_state.logger") as logger:
        result = await node({"thread_id": "thread-1", "project_id": "project-1"})

    assert result["user_memory"] == {}
    logger.exception.assert_called_once()
    assert (
        logger.exception.call_args.kwargs["extra"]["policy"] == "fallback_empty_memory"
    )


@pytest.mark.asyncio
async def test_load_state_indexes_memory_and_hydrates_dialog_state():
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(return_value=None)
    thread_runtime_state_repo.get_state_json = AsyncMock(return_value={})

    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])

    memory_repo = MagicMock()
    memory_repo.get_for_user_view = AsyncMock(
        return_value=[
            MemoryEntryView(
                id="memory-1",
                key="dialog_state",
                value={"repeat_count": 2, "last_topic": "pricing"},
                type="dialog_state",
            ),
            MemoryEntryView(
                id="memory-2",
                key="contact_preference",
                value={"preferred_channel": "chat", "avoid_calls": True},
                type="preferences",
            ),
        ]
    )

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=memory_repo,
    )

    result = await node({"thread_id": "thread-1", "project_id": "project-1"})

    assert result["user_memory"] == {
        "dialog_state": [
            {
                "key": "dialog_state",
                "value": {"repeat_count": 2, "last_topic": "pricing"},
            }
        ],
        "preferences": [
            {
                "key": "contact_preference",
                "value": {"preferred_channel": "chat", "avoid_calls": True},
            }
        ],
    }
    assert result["dialog_state"]["repeat_count"] == 2
    assert result["dialog_state"]["last_topic"] == "pricing"


@pytest.mark.asyncio
async def test_load_state_reconstruction_does_not_restore_persisted_transient_execution_state():
    turn_one_context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "response_text": "done",
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_name": "crm.get_user",
            "tool_args": {"telegram_id": 1},
            "tool_result": {"found": True},
            "tool_execution_status": "succeeded",
            "tool_execution_safe_error_code": None,
            "tool_response_text": "Done.",
            "knowledge_chunks": [{"id": "old", "content": "old"}],
            "knowledge_retrieval_status": "retrieved",
            "knowledge_retrieval_error_type": None,
            "model_answerability": "supported",
            "supporting_entry_ids": ["old"],
            "unsupported_aspects": [],
            "generation_output_parse_status": "valid",
            "generation_schema_status": "valid",
            "evidence_reference_status": "valid",
            "semantic_grounding_status": "unchecked",
            "semantic_grounding_failure_reason": None,
            "fallback_reason": None,
            "generated_action_cta_detected": False,
            "canonical_response_cta": None,
        }
    )
    assert turn_one_context.state_payload is not None

    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(return_value=None)
    thread_runtime_state_repo.get_state_json = AsyncMock(
        return_value=turn_one_context.state_payload
    )
    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=None,
    )

    result = await node({"thread_id": "thread-1"})

    for field in (
        "generation_mode",
        "tool_name",
        "tool_args",
        "tool_result",
        "tool_execution_status",
        "tool_execution_safe_error_code",
        "tool_response_text",
        "knowledge_chunks",
        "knowledge_retrieval_status",
        "knowledge_retrieval_error_type",
        "model_answerability",
        "supporting_entry_ids",
        "unsupported_aspects",
        "generation_output_parse_status",
        "generation_schema_status",
        "evidence_reference_status",
        "semantic_grounding_status",
        "semantic_grounding_failure_reason",
        "fallback_reason",
        "generated_action_cta_detected",
        "canonical_response_cta",
    ):
        assert field not in result


@pytest.mark.asyncio
async def test_load_state_reconstructs_handoff_ticket_identity_after_persistence_round_trip():
    turn_one_context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "handoff partial failure",
            "requires_human": False,
            "ticket_created": True,
            "handoff_ticket_id": "ticket-123",
            "escalation_failed": True,
            "handoff_completed": False,
            "thread_waiting_manager": False,
            "notification_degraded": False,
            "lifecycle": "active_client",
            "dialog_state": {
                "lifecycle": "active_client",
                "lead_status": "active_client",
            },
            "response_text": "technical failure text",
            "tool_result": {"ticket_id": "ticket-123"},
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "failed",
            "tool_execution_safe_error_code": "handoff_state_transition_failed",
        }
    )
    assert turn_one_context.state_payload is not None

    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(
        return_value={
            "id": "thread-1",
            "client_id": "client-1",
            "project_id": "project-1",
            "status": "active",
            "context_summary": "summary",
        }
    )
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.get_analytics_view = AsyncMock(return_value=None)
    thread_runtime_state_repo.get_state_json = AsyncMock(
        return_value=turn_one_context.state_payload
    )
    thread_message_repo = MagicMock()
    thread_message_repo.get_messages_for_langgraph = AsyncMock(return_value=[])

    node = create_load_state_node(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        project_repo=MagicMock(),
        memory_repo=None,
    )

    result = await node({"thread_id": "thread-1"})

    assert result["ticket_created"] is True
    assert result["handoff_ticket_id"] == "ticket-123"
    assert result["escalation_failed"] is True
    assert result["handoff_completed"] is False
    assert result["thread_waiting_manager"] is False
    assert result["notification_degraded"] is False
    assert result["requires_human"] is False
    assert "response_text" not in result
    assert "tool_result" not in result
    assert "generation_mode" not in result
    assert "tool_execution_status" not in result
    assert "tool_execution_safe_error_code" not in result
