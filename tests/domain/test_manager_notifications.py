from src.domain.project_plane.manager_notifications import (
    ManagerNotificationTarget,
    select_manager_notification_targets,
)


def test_select_manager_notification_targets_prefers_canonical_user_id():
    targets = [
        ManagerNotificationTarget(user_id="user-1", telegram_chat_id="111"),
        ManagerNotificationTarget(user_id="user-2", telegram_chat_id="222"),
    ]

    selected = select_manager_notification_targets(targets, manager_user_id="user-2")

    assert selected == [ManagerNotificationTarget(user_id="user-2", telegram_chat_id="222")]


def test_select_manager_notification_targets_falls_back_to_transport_chat_id():
    targets = [
        ManagerNotificationTarget(user_id="user-1", telegram_chat_id="111"),
        ManagerNotificationTarget(user_id="user-2", telegram_chat_id="222"),
    ]

    selected = select_manager_notification_targets(targets, manager_chat_id="111")

    assert selected == [ManagerNotificationTarget(user_id="user-1", telegram_chat_id="111")]


def test_select_manager_notification_targets_preserves_legacy_bridge_target_when_missing():
    targets = [ManagerNotificationTarget(user_id="user-1", telegram_chat_id="111")]

    selected = select_manager_notification_targets(
        targets,
        manager_user_id="user-2",
        manager_chat_id="999",
    )

    assert selected == [ManagerNotificationTarget(user_id="user-2", telegram_chat_id="999")]
