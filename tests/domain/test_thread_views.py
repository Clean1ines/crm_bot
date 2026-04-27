from datetime import datetime
from uuid import uuid4

from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadDialogClientView,
    ThreadDialogView,
    ThreadLastMessageView,
    ThreadMessageCounts,
    ThreadMessageView,
    ThreadRuntimeMessageView,
    ThreadStatusSummaryView,
    ThreadWithProjectView,
)


def test_thread_with_project_view_normalizes_uuid_fields_and_serializes_record():
    thread_id = uuid4()
    client_id = uuid4()
    project_id = uuid4()
    manager_user_id = uuid4()
    created_at = datetime.now()
    updated_at = datetime.now()

    view = ThreadWithProjectView.from_record(
        {
            "id": thread_id,
            "client_id": client_id,
            "status": "manual",
            "manager_user_id": manager_user_id,
            "manager_chat_id": "123",
            "context_summary": "summary",
            "created_at": created_at,
            "updated_at": updated_at,
            "project_id": project_id,
            "full_name": "Client Name",
            "username": "client",
            "chat_id": 555,
        }
    )

    assert view is not None
    assert view.thread_id == str(thread_id)
    assert view.client_id == str(client_id)
    assert view.project_id == str(project_id)
    assert view.manager_user_id == str(manager_user_id)
    assert view.to_record() == {
        "id": str(thread_id),
        "client_id": str(client_id),
        "status": "manual",
        "manager_user_id": str(manager_user_id),
        "manager_chat_id": "123",
        "context_summary": "summary",
        "created_at": created_at,
        "updated_at": updated_at,
        "project_id": str(project_id),
        "full_name": "Client Name",
        "username": "client",
        "chat_id": 555,
    }


def test_thread_with_project_view_returns_none_for_empty_record():
    assert ThreadWithProjectView.from_record(None) is None
    assert ThreadWithProjectView.from_record({}) is None


def test_thread_analytics_view_roundtrip():
    view = ThreadAnalyticsView.from_record(
        {
            "intent": "pricing",
            "lifecycle": "warm",
            "cta": "book_call",
            "decision": "RESPOND_KB",
        }
    )

    assert view == ThreadAnalyticsView(
        intent="pricing",
        lifecycle="warm",
        cta="book_call",
        decision="RESPOND_KB",
    )
    assert view.to_record() == {
        "intent": "pricing",
        "lifecycle": "warm",
        "cta": "book_call",
        "decision": "RESPOND_KB",
    }


def test_thread_analytics_view_returns_none_for_empty_record():
    assert ThreadAnalyticsView.from_record(None) is None
    assert ThreadAnalyticsView.from_record({}) is None


def test_thread_message_counts_defaults_missing_values_to_zero():
    counts = ThreadMessageCounts.from_record(None)

    assert counts == ThreadMessageCounts(total=0, ai=0, manager=0)
    assert counts.to_record() == {"total": 0, "ai": 0, "manager": 0}


def test_thread_dialog_view_serializes_nested_payloads():
    view = ThreadDialogView(
        thread_id="thread-1",
        status="active",
        interaction_mode="ai",
        thread_created_at="2025-01-01T00:00:00",
        thread_updated_at="2025-01-02T00:00:00",
        client=ThreadDialogClientView(
            id="client-1",
            full_name="Client Name",
            username="client",
            chat_id=123,
        ),
        last_message=ThreadLastMessageView(
            content="hello",
            created_at="2025-01-02T00:00:00",
        ),
        unread_count=0,
    )

    assert view.to_record() == {
        "thread_id": "thread-1",
        "status": "active",
        "interaction_mode": "ai",
        "thread_created_at": "2025-01-01T00:00:00",
        "thread_updated_at": "2025-01-02T00:00:00",
        "client": {
            "id": "client-1",
            "full_name": "Client Name",
            "username": "client",
            "chat_id": 123,
        },
        "last_message": {
            "content": "hello",
            "created_at": "2025-01-02T00:00:00",
        },
        "unread_count": 0,
    }


def test_thread_message_view_serializes_metadata_copy():
    metadata = {"source": "test"}
    view = ThreadMessageView(
        id="message-1",
        role="assistant",
        content="hello",
        created_at="2025-01-01T00:00:00",
        metadata=metadata,
    )

    record = view.to_record()
    assert record == {
        "id": "message-1",
        "role": "assistant",
        "content": "hello",
        "created_at": "2025-01-01T00:00:00",
        "metadata": {"source": "test"},
    }

    record["metadata"]["source"] = "mutated"
    assert view.metadata == {"source": "test"}


def test_thread_runtime_message_view_exposes_typed_attributes():
    view = ThreadRuntimeMessageView(role="user", content="hello")

    assert view.role == "user"
    assert view.content == "hello"
    assert view.to_record() == {"role": "user", "content": "hello"}

def test_thread_runtime_message_view_does_not_expose_mapping_compatibility():
    view = ThreadRuntimeMessageView(role="user", content="hello")

    assert not hasattr(view, "__getitem__")

def test_thread_status_summary_view_normalizes_record():
    thread_id = uuid4()
    client_id = uuid4()

    view = ThreadStatusSummaryView.from_record(
        {
            "id": thread_id,
            "client_id": client_id,
            "status": "active",
            "client_name": "Client Name",
        }
    )

    assert view.to_record() == {
        "id": str(thread_id),
        "client_id": str(client_id),
        "status": "active",
        "client_name": "Client Name",
    }
