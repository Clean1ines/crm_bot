from unittest.mock import MagicMock

from src.application.orchestration.client_message_service import ClientMessageService
from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)
from src.application.orchestration.manager_reply_service import ManagerReplyService


def _agent_factory(**_kwargs):
    return MagicMock()


def test_client_message_service_uses_split_thread_repositories():
    lifecycle = MagicMock(name="thread_lifecycle_repo")
    messages = MagicMock(name="thread_message_repo")
    read = MagicMock(name="thread_read_repo")

    service = ClientMessageService(
        threads=lifecycle,
        thread_messages=messages,
        thread_read=read,
        queue_repo=MagicMock(),
        runtime_guards=MagicMock(),
        runtime_loader=MagicMock(),
        graph_factory=MagicMock(),
        graph_executor=MagicMock(),
        thread_lock=MagicMock(),
        cache_factory=None,
        event_emitter=MagicMock(),
        logger=MagicMock(),
    )

    assert service.threads is lifecycle
    assert service.thread_messages is messages
    assert service.thread_read is read


def test_manager_reply_service_uses_split_thread_repositories():
    lifecycle = MagicMock(name="thread_lifecycle_repo")
    messages = MagicMock(name="thread_message_repo")
    read = MagicMock(name="thread_read_repo")

    service = ManagerReplyService(
        projects=MagicMock(),
        threads=lifecycle,
        thread_messages=messages,
        thread_read=read,
        telegram_client=MagicMock(),
        event_emitter=MagicMock(),
        logger=MagicMock(),
    )

    assert service.threads is lifecycle
    assert service.thread_messages is messages
    assert service.thread_read is read


def test_conversation_orchestrator_wires_client_and_manager_services_to_split_thread_repos():
    lifecycle = MagicMock(name="thread_lifecycle_repo")
    messages = MagicMock(name="thread_message_repo")
    runtime_state = MagicMock(name="thread_runtime_state_repo")
    read = MagicMock(name="thread_read_repo")

    orchestrator = ConversationOrchestrator(
        db_conn=MagicMock(),
        project_repo=MagicMock(),
        thread_lifecycle_repo=lifecycle,
        thread_message_repo=messages,
        thread_runtime_state_repo=runtime_state,
        thread_read_repo=read,
        queue_repo=MagicMock(),
        event_repo=MagicMock(),
        tool_registry=MagicMock(),
        memory_repo=MagicMock(),
        logger=MagicMock(),
        agent_factory=_agent_factory,
    )

    assert orchestrator.client_messages.threads is lifecycle
    assert orchestrator.client_messages.thread_messages is messages
    assert orchestrator.client_messages.thread_read is read

    assert orchestrator.manager_replies.threads is lifecycle
    assert orchestrator.manager_replies.thread_messages is messages
    assert orchestrator.manager_replies.thread_read is read
