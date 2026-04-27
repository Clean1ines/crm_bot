from dataclasses import dataclass, field
from typing import Any
import json

def _ensure_metadata_dict(metadata: Any) -> dict:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {}
    return dict(metadata) if hasattr(metadata, '__iter__') else {}

@dataclass(slots=True)
class ClientListItemView:
    id: str
    user_id: str | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    company: str | None = None
    phone: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chat_id: int | None = None
    source: str | None = None
    created_at: str | None = None
    last_activity_at: str | None = None
    threads_count: int = 0
    latest_thread_id: str | None = None

    def to_record(self) -> dict[str, Any]:
        metadata_dict = _ensure_metadata_dict(self.metadata)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "company": self.company,
            "phone": self.phone,
            "metadata": metadata_dict.copy(),
            "chat_id": self.chat_id,
            "source": self.source,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "threads_count": self.threads_count,
            "latest_thread_id": self.latest_thread_id,
        }


@dataclass(slots=True)
class ClientListView:
    clients: list[ClientListItemView] = field(default_factory=list)
    total_clients: int = 0
    new_clients_7d: int = 0
    active_dialogs: int = 0

    def to_record(self) -> dict[str, Any]:
        return {
            "clients": [client.to_record() for client in self.clients],
            "stats": {
                "total_clients": self.total_clients,
                "new_clients_7d": self.new_clients_7d,
                "active_dialogs": self.active_dialogs,
            },
        }


@dataclass(slots=True)
class ClientDetailView:
    id: str
    user_id: str | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    company: str | None = None
    phone: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chat_id: int | None = None
    source: str | None = None
    created_at: str | None = None

    def to_record(self) -> dict[str, Any]:
        metadata_dict = _ensure_metadata_dict(self.metadata)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "company": self.company,
            "phone": self.phone,
            "metadata": metadata_dict.copy(),
            "chat_id": self.chat_id,
            "source": self.source,
            "created_at": self.created_at,
        }
