import json

from src.domain.project_plane.manager_assignments import (
    ManagerReplySession,
    build_manager_audit_payload,
)


def test_reply_session_serializes_canonical_identity_and_transport_bridge():
    session = ManagerReplySession.for_telegram_manager(
        thread_id="thread-1",
        manager_user_id="user-1",
        manager_chat_id="12345",
    )

    assert session.thread_key == "awaiting_reply_thread:thread-1"
    assert session.manager_key == "awaiting_reply:12345"
    assert json.loads(session.to_redis_value()) == {
        "manager_chat_id": "12345",
        "manager_user_id": "user-1",
        "has_manager_reply": False,
        "claimed_at_unix": None,
    }


def test_reply_session_parses_legacy_plain_chat_id_payload():
    session = ManagerReplySession.from_redis_value(
        thread_id="thread-1",
        raw_value="12345",
    )

    assert session is not None
    assert session.manager_chat_id == "12345"
    assert session.manager_user_id == ""


def test_reply_session_parses_canonical_json_payload():
    session = ManagerReplySession.from_redis_value(
        thread_id="thread-1",
        raw_value='{"manager_chat_id":"12345","manager_user_id":"user-1","has_manager_reply":true,"claimed_at_unix":123}',
    )

    assert session is not None
    assert session.manager_chat_id == "12345"
    assert session.manager_user_id == "user-1"
    assert session.has_manager_reply is True
    assert session.claimed_at_unix == 123


def test_platform_reply_session_omits_transport_bridge():
    session = ManagerReplySession.for_platform_manager(
        thread_id="thread-1",
        manager_user_id="user-1",
        claimed_at_unix=456,
    )

    assert session.manager_key is None
    assert json.loads(session.to_redis_value()) == {
        "manager_chat_id": None,
        "manager_user_id": "user-1",
        "has_manager_reply": False,
        "claimed_at_unix": 456,
    }


def test_build_manager_audit_payload_keeps_transport_out_of_top_level_identity():
    payload = build_manager_audit_payload(
        manager_user_id="user-1",
        manager_chat_id="12345",
    )

    assert payload == {
        "manager_user_id": "user-1",
        "manager_transport": {
            "kind": "telegram",
            "chat_id": "12345",
        },
    }
