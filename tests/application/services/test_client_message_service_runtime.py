from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.orchestration.client_message_service import (
    ClientMessageService,
    MANAGER_RECOVERY_FAILED_TEXT,
    MANAGER_TICKET_CLOSED_TEXT,
    MANAGER_WAIT_RECORDED_TEXT,
    PENDING_MANAGER_TICKET_TEXT,
    RETURNED_TO_ASSISTANT_TEXT,
)
from src.domain.project_plane.manager_assignments import ManagerReplySession
from src.domain.project_plane.thread_status import ThreadStatus


PROJECT_ID = "project-1"
THREAD_ID = "thread-1"
CLIENT_ID = "client-1"
CHAT_ID = 12345


class FakeCache:
    def __init__(self, value=None) -> None:
        self.value = value
        self.get = AsyncMock(return_value=value)
        self.delete = AsyncMock()


def _thread_view(status: str, *, manager_user_id=None, manager_chat_id=None):
    record = {
        "id": THREAD_ID,
        "client_id": CLIENT_ID,
        "project_id": PROJECT_ID,
        "status": status,
        "manager_user_id": manager_user_id,
        "manager_chat_id": manager_chat_id,
        "chat_id": CHAT_ID,
    }
    return SimpleNamespace(
        updated_at=datetime.now(UTC),
        to_record=lambda: record,
    )


def _outcome(text: str, *, delivered: bool = False):
    return SimpleNamespace(text=text, delivered=delivered)


def _service(
    *,
    status: str,
    cache_value=None,
    manager_user_id=None,
    manager_chat_id=None,
    manager_replies_override=...,
):
    threads = MagicMock()
    threads.get_or_create_client = AsyncMock(return_value=CLIENT_ID)
    threads.get_active_thread = AsyncMock(return_value=THREAD_ID)
    threads.create_thread = AsyncMock(return_value=THREAD_ID)

    thread_messages = MagicMock()
    thread_messages.add_message = AsyncMock()
    thread_messages.get_messages_for_langgraph = AsyncMock(return_value=[])

    thread_read = MagicMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=_thread_view(
            status,
            manager_user_id=manager_user_id,
            manager_chat_id=manager_chat_id,
        )
    )

    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()

    runtime_guards = MagicMock()
    runtime_guards.allow_request = AsyncMock(return_value=True)
    runtime_guards.try_acquire_thread_slot = AsyncMock(return_value=True)
    runtime_guards.release_thread_slot = AsyncMock()

    runtime_loader = MagicMock()
    runtime_loader.load_project_configuration = AsyncMock(
        return_value=SimpleNamespace(to_dict=lambda: {})
    )

    graph_factory = MagicMock()
    graph_factory.get_graph_for_project = AsyncMock(return_value=MagicMock())

    graph_executor = MagicMock()
    graph_executor.outcome = MagicMock(side_effect=_outcome)
    graph_executor.trim_recent_history = MagicMock(return_value=[])
    graph_executor.create_graph_execution_request = MagicMock(return_value={})
    graph_executor.invoke_graph = AsyncMock(return_value=_outcome("AI response"))

    thread_lock = MagicMock()
    thread_lock.acquire_thread_lock = AsyncMock(return_value=True)
    thread_lock.release_thread_lock = AsyncMock()

    cache = FakeCache(cache_value)
    event_emitter = MagicMock()
    event_emitter.emit_event = AsyncMock()
    manager_replies = MagicMock()
    manager_replies.close_thread_for_manager = AsyncMock()
    if manager_replies_override is not ...:
        manager_replies = manager_replies_override

    logger = MagicMock()
    service = ClientMessageService(
        threads=threads,
        thread_messages=thread_messages,
        thread_read=thread_read,
        manager_replies=manager_replies,
        queue_repo=queue_repo,
        runtime_guards=runtime_guards,
        runtime_loader=runtime_loader,
        graph_factory=graph_factory,
        graph_executor=graph_executor,
        thread_lock=thread_lock,
        cache_factory=AsyncMock(return_value=cache),
        event_emitter=event_emitter,
        logger=logger,
    )
    return service, SimpleNamespace(
        threads=threads,
        thread_messages=thread_messages,
        queue_repo=queue_repo,
        graph_factory=graph_factory,
        graph_executor=graph_executor,
        thread_lock=thread_lock,
        cache=cache,
        event_emitter=event_emitter,
        manager_replies=manager_replies,
        thread_read=thread_read,
        logger=logger,
    )


@pytest.mark.asyncio
async def test_waiting_manager_without_session_holds_message_and_does_not_invoke_graph():
    service, deps = _service(status=ThreadStatus.WAITING_MANAGER.value)

    result = await service.process_message(
        PROJECT_ID, CHAT_ID, "А пока расскажи про роли"
    )

    assert result == PENDING_MANAGER_TICKET_TEXT
    deps.thread_messages.add_message.assert_awaited_once_with(
        THREAD_ID,
        role="user",
        content="А пока расскажи про роли",
    )
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()
    deps.queue_repo.enqueue.assert_not_awaited()
    deps.threads.create_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_manager_without_session_return_to_assistant_closes_ticket_and_next_turn_runs_graph():
    service, deps = _service(status=ThreadStatus.WAITING_MANAGER.value)

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "вернуться к ассистенту",
    )

    assert result == RETURNED_TO_ASSISTANT_TEXT
    deps.thread_messages.add_message.assert_awaited_once_with(
        THREAD_ID,
        role="user",
        content="вернуться к ассистенту",
    )
    deps.manager_replies.close_thread_for_manager.assert_awaited_once_with(
        THREAD_ID,
        manually_closed=False,
        close_reason="client_returned_to_assistant",
    )
    deps.cache.delete.assert_awaited_once_with(f"awaiting_reply_thread:{THREAD_ID}")
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()

    deps.thread_messages.add_message.reset_mock()
    deps.graph_factory.get_graph_for_project.reset_mock()
    deps.graph_executor.invoke_graph.reset_mock()
    deps.thread_read.get_thread_with_project_view.return_value = _thread_view(
        ThreadStatus.ACTIVE.value
    )

    next_result = await service.process_message(
        PROJECT_ID, CHAT_ID, "Что умеет сервис?"
    )

    assert next_result == "AI response"
    deps.graph_factory.get_graph_for_project.assert_awaited_once_with(PROJECT_ID)
    deps.graph_executor.invoke_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_waiting_manager_return_to_assistant_does_not_clear_redis_when_manager_replies_missing():
    service, deps = _service(
        status=ThreadStatus.WAITING_MANAGER.value,
        manager_replies_override=None,
    )

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "вернуться к ассистенту",
    )

    assert result == MANAGER_RECOVERY_FAILED_TEXT
    deps.thread_messages.add_message.assert_awaited_once_with(
        THREAD_ID,
        role="user",
        content="вернуться к ассистенту",
    )
    deps.cache.delete.assert_not_awaited()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_manager_return_to_assistant_does_not_clear_redis_when_close_fails():
    service, deps = _service(status=ThreadStatus.WAITING_MANAGER.value)
    deps.manager_replies.close_thread_for_manager.side_effect = RuntimeError(
        "close failed"
    )

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "вернуться к ассистенту",
    )

    assert result == MANAGER_RECOVERY_FAILED_TEXT
    deps.manager_replies.close_thread_for_manager.assert_awaited_once_with(
        THREAD_ID,
        manually_closed=False,
        close_reason="client_returned_to_assistant",
    )
    deps.cache.delete.assert_not_awaited()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()
    deps.logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_waiting_manager_with_session_return_to_assistant_clears_session_notifies_no_manager():
    session = ManagerReplySession.for_telegram_manager(
        thread_id=THREAD_ID,
        manager_user_id="manager-1",
        manager_chat_id="987",
    )
    service, deps = _service(
        status=ThreadStatus.WAITING_MANAGER.value,
        cache_value=session.to_redis_value(),
    )

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "вернуться к ассистенту",
    )

    assert result == RETURNED_TO_ASSISTANT_TEXT
    deps.manager_replies.close_thread_for_manager.assert_awaited_once_with(
        THREAD_ID,
        manually_closed=False,
        close_reason="client_returned_to_assistant",
    )
    deps.cache.delete.assert_any_await("awaiting_reply:987")
    deps.cache.delete.assert_any_await(f"awaiting_reply_thread:{THREAD_ID}")
    deps.queue_repo.enqueue.assert_not_awaited()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_manager_return_to_assistant_closes_ticket_before_clearing_redis():
    session = ManagerReplySession.for_telegram_manager(
        thread_id=THREAD_ID,
        manager_user_id="manager-1",
        manager_chat_id="987",
    )
    service, deps = _service(
        status=ThreadStatus.WAITING_MANAGER.value,
        cache_value=session.to_redis_value(),
    )
    operations: list[str] = []

    async def close_ticket(*args, **kwargs):
        operations.append("close_thread_for_manager")

    async def delete_key(key):
        operations.append(f"redis.delete:{key}")

    deps.manager_replies.close_thread_for_manager.side_effect = close_ticket
    deps.cache.delete.side_effect = delete_key

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "вернуться к ассистенту",
    )

    assert result == RETURNED_TO_ASSISTANT_TEXT
    assert operations == [
        "close_thread_for_manager",
        "redis.delete:awaiting_reply:987",
        f"redis.delete:awaiting_reply_thread:{THREAD_ID}",
    ]


@pytest.mark.asyncio
async def test_waiting_manager_close_resolved_closes_ticket_without_graph():
    service, deps = _service(status=ThreadStatus.WAITING_MANAGER.value)

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "закрыть обращение: решено",
    )

    assert result == MANAGER_TICKET_CLOSED_TEXT
    deps.manager_replies.close_thread_for_manager.assert_awaited_once_with(
        THREAD_ID,
        manually_closed=False,
        close_reason="client_resolved",
    )
    deps.cache.delete.assert_awaited_once_with(f"awaiting_reply_thread:{THREAD_ID}")
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_manager_close_resolved_closes_ticket_before_clearing_redis():
    service, deps = _service(status=ThreadStatus.WAITING_MANAGER.value)
    operations: list[str] = []

    async def close_ticket(*args, **kwargs):
        operations.append("close_thread_for_manager")

    async def delete_key(key):
        operations.append(f"redis.delete:{key}")

    deps.manager_replies.close_thread_for_manager.side_effect = close_ticket
    deps.cache.delete.side_effect = delete_key

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "закрыть обращение: решено",
    )

    assert result == MANAGER_TICKET_CLOSED_TEXT
    assert operations == [
        "close_thread_for_manager",
        f"redis.delete:awaiting_reply_thread:{THREAD_ID}",
    ]


@pytest.mark.asyncio
async def test_waiting_manager_long_wait_records_event_without_closing_or_graph():
    service, deps = _service(status=ThreadStatus.WAITING_MANAGER.value)

    result = await service.process_message(PROJECT_ID, CHAT_ID, "долго жду")

    assert result == MANAGER_WAIT_RECORDED_TEXT
    deps.event_emitter.emit_event.assert_any_await(
        stream_id=THREAD_ID,
        project_id=PROJECT_ID,
        event_type="manager_waiting_reminder",
        payload={
            "message": "долго жду",
            "manager_user_id": None,
            "manager_chat_id": None,
        },
    )
    deps.manager_replies.close_thread_for_manager.assert_not_awaited()
    deps.queue_repo.enqueue.assert_not_awaited()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_waiting_manager_with_session_preserves_manager_notification_path():
    session = ManagerReplySession.for_telegram_manager(
        thread_id=THREAD_ID,
        manager_user_id="manager-1",
        manager_chat_id="987",
    )
    service, deps = _service(
        status=ThreadStatus.WAITING_MANAGER.value,
        cache_value=session.to_redis_value(),
    )

    result = await service.process_message(PROJECT_ID, CHAT_ID, "Есть ещё вопрос")

    assert result == PENDING_MANAGER_TICKET_TEXT
    deps.thread_messages.add_message.assert_awaited_once()
    deps.queue_repo.enqueue.assert_awaited_once()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_thread_still_invokes_graph():
    service, deps = _service(status=ThreadStatus.ACTIVE.value)

    result = await service.process_message(PROJECT_ID, CHAT_ID, "Что умеет сервис?")

    assert result == "AI response"
    deps.graph_factory.get_graph_for_project.assert_awaited_once_with(PROJECT_ID)
    deps.graph_executor.create_graph_execution_request.assert_called_once()
    assert (
        deps.graph_executor.create_graph_execution_request.call_args.kwargs["question"]
        == "Что умеет сервис?"
    )
    deps.graph_executor.invoke_graph.assert_awaited_once()
    deps.thread_messages.add_message.assert_awaited_once_with(
        THREAD_ID, role="user", content="Что умеет сервис?"
    )
    deps.thread_lock.acquire_thread_lock.assert_awaited_once_with(THREAD_ID)
    deps.thread_lock.release_thread_lock.assert_awaited_once_with(THREAD_ID)


@pytest.mark.asyncio
async def test_multi_question_message_is_one_atomic_graph_turn():
    service, deps = _service(status=ThreadStatus.ACTIVE.value)
    message = (
        "Можно ли использовать Axole для медицинских или юридических консультаций?\n"
        "За сколько дней можно запустить бота?"
    )

    result = await service.process_message(PROJECT_ID, CHAT_ID, message)

    assert result == "AI response"
    deps.thread_messages.add_message.assert_awaited_once_with(
        THREAD_ID, role="user", content=message
    )
    deps.graph_factory.get_graph_for_project.assert_awaited_once_with(PROJECT_ID)
    deps.graph_executor.create_graph_execution_request.assert_called_once()
    assert deps.graph_executor.create_graph_execution_request.call_args.kwargs[
        "question"
    ] == message
    deps.graph_executor.invoke_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_punctuation_inside_message_does_not_create_additional_graph_turns():
    service, deps = _service(status=ThreadStatus.ACTIVE.value)
    message = "Привет! Подскажите, Axole работает с CRM? Это важно."

    result = await service.process_message(PROJECT_ID, CHAT_ID, message)

    assert result == "AI response"
    deps.thread_messages.add_message.assert_awaited_once_with(
        THREAD_ID, role="user", content=message
    )
    deps.graph_executor.create_graph_execution_request.assert_called_once()
    assert deps.graph_executor.create_graph_execution_request.call_args.kwargs[
        "question"
    ] == message
    deps.graph_executor.invoke_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_thread_returns_single_graph_outcome_normally():
    service, deps = _service(status=ThreadStatus.ACTIVE.value)
    deps.graph_executor.invoke_graph.return_value = _outcome("Single answer")

    result = await service.process_message(
        PROJECT_ID, CHAT_ID, "Первый вопрос? Второй вопрос?"
    )

    assert result == "Single answer"
    deps.graph_executor.invoke_graph.assert_awaited_once()
    deps.graph_executor.outcome.assert_called_once_with("Single answer")


@pytest.mark.asyncio
async def test_manual_thread_without_redis_session_keeps_existing_manager_behavior():
    service, deps = _service(
        status=ThreadStatus.MANUAL.value,
        manager_user_id="manager-1",
    )

    result = await service.process_message(PROJECT_ID, CHAT_ID, "Есть ещё вопрос")

    assert result == PENDING_MANAGER_TICKET_TEXT
    deps.thread_messages.add_message.assert_awaited_once()
    deps.manager_replies.close_thread_for_manager.assert_not_awaited()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_thread_recovery_command_does_not_take_ticket_from_manager():
    service, deps = _service(
        status=ThreadStatus.MANUAL.value,
        manager_user_id="manager-1",
    )

    result = await service.process_message(
        PROJECT_ID,
        CHAT_ID,
        "вернуться к ассистенту",
    )

    assert result == PENDING_MANAGER_TICKET_TEXT
    deps.manager_replies.close_thread_for_manager.assert_not_awaited()
    deps.graph_factory.get_graph_for_project.assert_not_awaited()
    deps.graph_executor.invoke_graph.assert_not_awaited()
