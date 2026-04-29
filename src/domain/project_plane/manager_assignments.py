"""Domain objects for manager assignment and Telegram reply sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.domain.project_plane.json_types import JsonObject


RedisSessionValue = bytes | str | None


@dataclass(frozen=True)
class ManagerActor:
    """Canonical manager identity with optional Telegram transport binding."""

    user_id: str
    telegram_chat_id: str | None = None


@dataclass(frozen=True)
class ManagerReplySession:
    """
    Manual-reply session for a claimed thread.

    Canonical identity is always `manager_user_id`. Telegram chat id remains an
    optional transport bridge while manager bot flows still exist.
    """

    thread_id: str
    manager_user_id: str
    manager_chat_id: str | None = None

    @property
    def thread_key(self) -> str:
        return f"awaiting_reply_thread:{self.thread_id}"

    @property
    def manager_key(self) -> str | None:
        if not self.manager_chat_id:
            return None
        return f"awaiting_reply:{self.manager_chat_id}"

    def to_redis_value(self) -> str:
        payload: JsonObject = {
            "manager_chat_id": self.manager_chat_id,
            "manager_user_id": self.manager_user_id,
        }
        return json.dumps(payload)

    @classmethod
    def for_telegram_manager(
        cls,
        *,
        thread_id: str,
        manager_user_id: str,
        manager_chat_id: str,
    ) -> "ManagerReplySession":
        return cls(
            thread_id=thread_id,
            manager_user_id=manager_user_id,
            manager_chat_id=manager_chat_id,
        )

    @classmethod
    def from_redis_value(
        cls,
        *,
        thread_id: str,
        raw_value: RedisSessionValue,
    ) -> "ManagerReplySession | None":
        """
        Parse both canonical JSON payloads and legacy plain-string chat ids.
        """
        if raw_value is None:
            return None

        decoded = raw_value.decode() if isinstance(raw_value, bytes) else raw_value
        if not decoded:
            return None

        try:
            parsed = json.loads(decoded)
        except (TypeError, json.JSONDecodeError):
            parsed = decoded

        if isinstance(parsed, dict):
            manager_user_id = parsed.get("manager_user_id")
            manager_chat_id = parsed.get("manager_chat_id")
            if not manager_user_id and not manager_chat_id:
                return None
            return cls(
                thread_id=thread_id,
                manager_user_id=str(manager_user_id) if manager_user_id else "",
                manager_chat_id=str(manager_chat_id) if manager_chat_id else None,
            )

        return cls(
            thread_id=thread_id,
            manager_user_id="",
            manager_chat_id=str(parsed),
        )


def build_manager_audit_payload(
    *,
    manager_user_id: str | None,
    manager_chat_id: str | None,
    manager_display_name: str | None = None,
) -> JsonObject:
    """
    Build canonical event/audit payload for manager-originated actions.

    `manager_user_id` is the domain identity. Telegram chat id, when present, is
    preserved only inside an explicit transport bridge block.
    """
    payload: JsonObject = {}
    if manager_user_id:
        payload["manager_user_id"] = manager_user_id
    if manager_display_name:
        payload["manager_identity"] = {"display_name": manager_display_name}
    if manager_chat_id:
        payload["manager_transport"] = {
            "kind": "telegram",
            "chat_id": str(manager_chat_id),
        }
    return payload
