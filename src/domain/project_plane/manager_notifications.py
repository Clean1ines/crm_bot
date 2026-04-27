"""Domain rules for project-plane manager notification routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ManagerNotificationTarget:
    """A project member who can receive manager-plane Telegram notifications."""

    user_id: str | None
    telegram_chat_id: str


def select_manager_notification_targets(
    targets: Iterable[ManagerNotificationTarget],
    *,
    manager_user_id: str | None = None,
    manager_chat_id: str | None = None,
) -> list[ManagerNotificationTarget]:
    """
    Select Telegram notification recipients for a manager-plane event.

    Priority:
    1. When manager_user_id is known, route to that canonical member.
    2. Otherwise fall back to Telegram transport identity.
    3. Otherwise broadcast to all eligible manager targets.
    4. If a legacy transport target is specified but not resolvable through
       memberships, preserve delivery through a temporary bridge target.
    """

    normalized_targets = list(targets)
    if manager_user_id:
        matched = [target for target in normalized_targets if target.user_id == manager_user_id]
        if matched:
            return matched

    if manager_chat_id:
        matched = [
            target for target in normalized_targets
            if target.telegram_chat_id == str(manager_chat_id)
        ]
        if matched:
            return matched
        return [
            ManagerNotificationTarget(
                user_id=manager_user_id,
                telegram_chat_id=str(manager_chat_id),
            )
        ]

    return normalized_targets
