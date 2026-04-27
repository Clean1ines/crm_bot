from uuid import uuid4

from src.domain.project_plane.thread_runtime import (
    ThreadAnalyticsSnapshot,
    ThreadRuntimeSnapshot,
)


def test_thread_runtime_snapshot_normalizes_repository_record():
    record = {
        "id": uuid4(),
        "client_id": uuid4(),
        "project_id": uuid4(),
        "status": "manual",
        "context_summary": "summary",
        "manager_user_id": uuid4(),
        "manager_chat_id": "123",
        "chat_id": 555,
    }

    snapshot = ThreadRuntimeSnapshot.from_record(record)

    assert snapshot is not None
    assert snapshot.thread_id == str(record["id"])
    assert snapshot.client_id == str(record["client_id"])
    assert snapshot.project_id == str(record["project_id"])
    assert snapshot.status == "manual"
    assert snapshot.context_summary == "summary"
    assert snapshot.manager_chat_id == "123"
    assert snapshot.chat_id == 555


def test_thread_analytics_snapshot_emits_state_patch_only_for_present_values():
    snapshot = ThreadAnalyticsSnapshot.from_record(
        {
            "intent": "pricing",
            "lifecycle": None,
            "cta": "book_consultation",
            "decision": "CALL_TOOL",
        }
    )

    assert snapshot.to_state_patch() == {
        "intent": "pricing",
        "cta": "book_consultation",
        "decision": "CALL_TOOL",
    }
