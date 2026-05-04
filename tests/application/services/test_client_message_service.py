from unittest.mock import AsyncMock, MagicMock
from datetime import UTC, datetime, timedelta

import pytest

from src.application.orchestration.client_message_service import (
    ClientMessageService,
    MANAGER_HANDOFF_TEXT,
)
from src.application.services.ticket_command_service import (
    MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS,
)
from src.domain.project_plane.manager_assignments import ManagerReplySession
from src.domain.project_plane.event_views import EventTimelineItemView
from src.domain.project_plane.thread_views import ThreadWithProjectView


def make_service(
    *,
    threads: object | None = None,
    thread_messages: object | None = None,
    thread_read: object | None = None,
    manager_replies: object | None = None,
    cache: object | None = None,
    event_reader: object | None = None,
) -> ClientMessageService:
    cache_factory = AsyncMock(return_value=cache) if cache is not None else None
    return ClientMessageService(
        threads=threads or AsyncMock(),
        thread_messages=thread_messages or AsyncMock(),
        thread_read=thread_read or AsyncMock(),
        manager_replies=manager_replies,
        event_reader=event_reader,
        queue_repo=AsyncMock(),
        runtime_guards=AsyncMock(),
        runtime_loader=AsyncMock(),
        graph_factory=AsyncMock(),
        graph_executor=MagicMock(
            outcome=MagicMock(
                side_effect=lambda text, delivered=False: MagicMock(text=text)
            )
        ),
        thread_lock=AsyncMock(),
        cache_factory=cache_factory,
        event_emitter=AsyncMock(),
        logger=MagicMock(),
    )


@pytest.mark.asyncio
async def test_try_redirect_to_platform_manager_records_message_without_ai_reply():
    session = ManagerReplySession.for_platform_manager(
        thread_id="thread-1",
        manager_user_id="manager-1",
    )
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=session.to_redis_value())
    thread_read = AsyncMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView(
            thread_id="thread-1",
            project_id="project-1",
            client_id="client-1",
            status="manual",
            chat_id=123,
        )
    )
    thread_messages = AsyncMock()

    service = make_service(
        thread_messages=thread_messages,
        thread_read=thread_read,
        cache=cache,
    )

    response = await service._try_redirect_to_manager(
        project_id="project-1",
        chat_id=123,
        thread_id="thread-1",
        thread_id_str="thread-1",
        text="Нужна помощь",
    )

    assert response == MANAGER_HANDOFF_TEXT
    thread_messages.add_message.assert_awaited_once_with(
        "thread-1",
        role="user",
        content="Нужна помощь",
    )
    service.event_emitter.emit_event.assert_awaited_once()
    service.queue_repo.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_try_redirect_to_telegram_manager_records_message_and_enqueues_notification():
    session = ManagerReplySession.for_telegram_manager(
        thread_id="thread-1",
        manager_user_id="manager-1",
        manager_chat_id="555",
    )
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=session.to_redis_value())
    thread_read = AsyncMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView(
            thread_id="thread-1",
            project_id="project-1",
            client_id="client-1",
            status="manual",
            chat_id=123,
        )
    )
    thread_messages = AsyncMock()

    service = make_service(
        thread_messages=thread_messages,
        thread_read=thread_read,
        cache=cache,
    )

    response = await service._try_redirect_to_manager(
        project_id="project-1",
        chat_id=123,
        thread_id="thread-1",
        thread_id_str="thread-1",
        text="Подскажите стоимость",
    )

    assert response == MANAGER_HANDOFF_TEXT
    thread_messages.add_message.assert_awaited_once_with(
        "thread-1",
        role="user",
        content="Подскажите стоимость",
    )
    service.queue_repo.enqueue.assert_awaited_once_with(
        task_type="notify_manager",
        payload={
            "thread_id": "thread-1",
            "project_id": "project-1",
            "message": "Подскажите стоимость",
            "target_manager_telegram_chat_id": "555",
            "manager_user_id": "manager-1",
        },
    )


@pytest.mark.asyncio
async def test_get_or_create_thread_keeps_manual_ticket_even_after_session_timeout():
    threads = AsyncMock()
    threads.get_active_thread = AsyncMock(return_value="thread-old")
    threads.create_thread = AsyncMock(return_value="thread-new")
    thread_read = AsyncMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView(
            thread_id="thread-old",
            project_id="project-1",
            client_id="client-1",
            status="manual",
            chat_id=123,
            updated_at=datetime.now(UTC)
            - timedelta(seconds=MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS + 1),
        )
    )
    manager_replies = AsyncMock()
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    event_reader = AsyncMock()
    event_reader.get_events_for_thread = AsyncMock(
        return_value=[
            EventTimelineItemView(
                id=1,
                type="manager_replied",
                payload={},
                ts=datetime.now(UTC)
                - timedelta(seconds=MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS + 1),
            )
        ]
    )

    service = make_service(
        threads=threads,
        thread_read=thread_read,
        manager_replies=manager_replies,
        cache=cache,
        event_reader=event_reader,
    )

    thread_id = await service._get_or_create_thread("project-1", "client-1")

    assert thread_id == "thread-old"
    manager_replies.close_thread_for_manager.assert_not_awaited()
    threads.create_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_thread_creates_new_thread_when_previous_is_closed():
    threads = AsyncMock()
    threads.get_active_thread = AsyncMock(return_value="thread-closed")
    threads.create_thread = AsyncMock(return_value="thread-new")
    thread_read = AsyncMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView(
            thread_id="thread-closed",
            project_id="project-1",
            client_id="client-1",
            status="closed",
            chat_id=123,
        )
    )

    service = make_service(
        threads=threads,
        thread_read=thread_read,
        manager_replies=AsyncMock(),
        cache=AsyncMock(),
        event_reader=AsyncMock(),
    )

    thread_id = await service._get_or_create_thread("project-1", "client-1")

    assert thread_id == "thread-new"
    threads.create_thread.assert_awaited_once_with("client-1")


@pytest.mark.asyncio
async def test_get_or_create_thread_keeps_manual_ticket_without_manager_reply_timeout():
    threads = AsyncMock()
    threads.get_active_thread = AsyncMock(return_value="thread-old")
    threads.create_thread = AsyncMock(return_value="thread-new")
    thread_read = AsyncMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView(
            thread_id="thread-old",
            project_id="project-1",
            client_id="client-1",
            status="manual",
            chat_id=123,
            manager_user_id="manager-1",
        )
    )
    manager_replies = AsyncMock()
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    event_reader = AsyncMock()
    event_reader.get_events_for_thread = AsyncMock(return_value=[])

    service = make_service(
        threads=threads,
        thread_read=thread_read,
        manager_replies=manager_replies,
        cache=cache,
        event_reader=event_reader,
    )

    thread_id = await service._get_or_create_thread("project-1", "client-1")

    assert thread_id == "thread-old"
    manager_replies.close_thread_for_manager.assert_not_awaited()
    threads.create_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_try_redirect_to_manager_uses_thread_assignment_when_redis_session_missing():
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    thread_read = AsyncMock()
    thread_read.get_thread_with_project_view = AsyncMock(
        return_value=ThreadWithProjectView(
            thread_id="thread-1",
            project_id="project-1",
            client_id="client-1",
            status="manual",
            chat_id=123,
            manager_user_id="manager-1",
        )
    )
    thread_messages = AsyncMock()

    service = make_service(
        thread_messages=thread_messages,
        thread_read=thread_read,
        cache=cache,
    )

    response = await service._try_redirect_to_manager(
        project_id="project-1",
        chat_id=123,
        thread_id="thread-1",
        thread_id_str="thread-1",
        text="Ответьте, пожалуйста",
    )

    assert response == MANAGER_HANDOFF_TEXT
    thread_messages.add_message.assert_awaited_once_with(
        "thread-1",
        role="user",
        content="Ответьте, пожалуйста",
    )
    service.queue_repo.enqueue.assert_not_awaited()
