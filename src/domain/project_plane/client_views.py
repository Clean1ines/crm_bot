from dataclasses import dataclass, field

from src.domain.display_names import build_display_name
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown


def _ensure_metadata_dict(metadata: JsonObject | str | None) -> JsonObject:
    if metadata is None:
        return {}
    return json_object_from_unknown(metadata)


@dataclass(slots=True)
class ClientListItemView:
    id: str
    user_id: str | None = None
    username: str | None = None
    full_name: str | None = None
    display_name: str | None = None
    email: str | None = None
    company: str | None = None
    phone: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    chat_id: int | None = None
    source: str | None = None
    created_at: str | None = None
    last_activity_at: str | None = None
    threads_count: int = 0
    latest_thread_id: str | None = None

    def __post_init__(self) -> None:
        self.display_name = self.display_name or build_display_name(
            full_name=self.full_name,
            username=self.username,
            email=self.email,
            fallback="Клиент",
        )

    def to_record(self) -> dict[str, object]:
        metadata_dict = _ensure_metadata_dict(self.metadata)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "display_name": self.display_name,
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

    def to_record(self) -> dict[str, object]:
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
    display_name: str | None = None
    email: str | None = None
    company: str | None = None
    phone: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    chat_id: int | None = None
    source: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        self.display_name = self.display_name or build_display_name(
            full_name=self.full_name,
            username=self.username,
            email=self.email,
            fallback="Клиент",
        )

    def to_record(self) -> dict[str, object]:
        metadata_dict = _ensure_metadata_dict(self.metadata)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "display_name": self.display_name,
            "email": self.email,
            "company": self.company,
            "phone": self.phone,
            "metadata": metadata_dict.copy(),
            "chat_id": self.chat_id,
            "source": self.source,
            "created_at": self.created_at,
        }
