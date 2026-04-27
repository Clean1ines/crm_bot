from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.domain.project_plane.json_types import json_object_from_unknown


@dataclass(frozen=True, slots=True)
class ManagerReplyHistoryItemView:
    id: int
    thread_id: str
    project_id: str
    manager_user_id: str
    text: str
    manager_chat_id: str | None = None
    created_at: datetime | str | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "ManagerReplyHistoryItemView":
        payload = json_object_from_unknown(record.get("payload"))
        transport = json_object_from_unknown(payload.get("manager_transport"))
        chat_id = transport.get("chat_id")
        created_at = record.get("created_at")

        return cls(
            id=int(record["id"]),
            thread_id=str(record["stream_id"]),
            project_id=str(record["project_id"]),
            manager_user_id=str(payload.get("manager_user_id") or ""),
            manager_chat_id=str(chat_id) if chat_id is not None else None,
            text=str(payload.get("text") or payload.get("message") or ""),
            created_at=created_at if isinstance(created_at, (datetime, str)) else None,
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "manager_user_id": self.manager_user_id,
            "manager_chat_id": self.manager_chat_id,
            "text": self.text,
            "created_at": self.created_at,
        }
