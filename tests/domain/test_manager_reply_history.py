from datetime import datetime
from uuid import uuid4

from src.domain.project_plane.manager_reply_history import ManagerReplyHistoryItemView


def test_manager_reply_history_item_view_reads_canonical_payload():
    project_id = str(uuid4())
    thread_id = str(uuid4())
    created_at = datetime(2026, 4, 27, 12, 0, 0)

    view = ManagerReplyHistoryItemView.from_record({
        "id": 10,
        "stream_id": thread_id,
        "project_id": project_id,
        "payload": {
            "manager_user_id": "manager-1",
            "text": "Здравствуйте",
            "manager_transport": {
                "kind": "telegram",
                "chat_id": "777",
            },
        },
        "created_at": created_at,
    })

    assert view.id == 10
    assert view.thread_id == thread_id
    assert view.project_id == project_id
    assert view.manager_user_id == "manager-1"
    assert view.manager_chat_id == "777"
    assert view.text == "Здравствуйте"
    assert view.created_at == created_at


def test_manager_reply_history_item_view_uses_empty_text_for_missing_payload():
    view = ManagerReplyHistoryItemView.from_record({
        "id": 1,
        "stream_id": "thread",
        "project_id": "project",
        "payload": {},
        "created_at": None,
    })

    assert view.manager_user_id == ""
    assert view.manager_chat_id is None
    assert view.text == ""
