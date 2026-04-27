from dataclasses import dataclass, field
from datetime import datetime

from src.domain.project_plane.json_types import JsonObject


@dataclass(slots=True)
class ThreadWithProjectView:
    thread_id: str
    client_id: str | None = None
    status: str | None = None
    manager_user_id: str | None = None
    manager_chat_id: str | None = None
    context_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    project_id: str | None = None
    full_name: str | None = None
    username: str | None = None
    chat_id: int | None = None

    @classmethod
    def from_record(cls, record: dict[str, object] | None) -> "ThreadWithProjectView | None":
        if not record:
            return None
        return cls(
            thread_id=str(record.get("id") or record.get("thread_id") or ""),
            client_id=str(record["client_id"]) if record.get("client_id") is not None else None,
            status=record.get("status"),
            manager_user_id=str(record["manager_user_id"]) if record.get("manager_user_id") is not None else None,
            manager_chat_id=str(record["manager_chat_id"]) if record.get("manager_chat_id") is not None else None,
            context_summary=record.get("context_summary"),
            created_at=record.get("created_at"),
            updated_at=record.get("updated_at"),
            project_id=str(record["project_id"]) if record.get("project_id") is not None else None,
            full_name=record.get("full_name"),
            username=record.get("username"),
            chat_id=record.get("chat_id"),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.thread_id,
            "client_id": self.client_id,
            "status": self.status,
            "manager_user_id": self.manager_user_id,
            "manager_chat_id": self.manager_chat_id,
            "context_summary": self.context_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_id": self.project_id,
            "full_name": self.full_name,
            "username": self.username,
            "chat_id": self.chat_id,
        }


@dataclass(slots=True)
class ThreadAnalyticsView:
    intent: str | None = None
    lifecycle: str | None = None
    cta: str | None = None
    decision: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object] | None) -> "ThreadAnalyticsView | None":
        if not record:
            return None
        return cls(
            intent=record.get("intent"),
            lifecycle=record.get("lifecycle"),
            cta=record.get("cta"),
            decision=record.get("decision"),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "lifecycle": self.lifecycle,
            "cta": self.cta,
            "decision": self.decision,
        }


@dataclass(slots=True)
class ThreadMessageCounts:
    total: int = 0
    ai: int = 0
    manager: int = 0

    @classmethod
    def from_record(cls, record: dict[str, object] | None) -> "ThreadMessageCounts":
        payload = record or {}
        return cls(
            total=int(payload.get("total") or 0),
            ai=int(payload.get("ai") or 0),
            manager=int(payload.get("manager") or 0),
        )

    def to_record(self) -> dict[str, int]:
        return {
            "total": self.total,
            "ai": self.ai,
            "manager": self.manager,
        }

@dataclass(slots=True)
class ThreadDialogClientView:
    id: str
    full_name: str | None = None
    username: str | None = None
    chat_id: int | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "username": self.username,
            "chat_id": self.chat_id,
        }


@dataclass(slots=True)
class ThreadLastMessageView:
    content: str
    created_at: str | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "content": self.content,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class ThreadDialogView:
    thread_id: str
    status: str
    interaction_mode: str | None
    thread_created_at: str | None
    thread_updated_at: str | None
    client: ThreadDialogClientView
    last_message: ThreadLastMessageView | None = None
    unread_count: int = 0

    def to_record(self) -> dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "status": self.status,
            "interaction_mode": self.interaction_mode,
            "thread_created_at": self.thread_created_at,
            "thread_updated_at": self.thread_updated_at,
            "client": self.client.to_record(),
            "last_message": self.last_message.to_record() if self.last_message else None,
            "unread_count": self.unread_count,
        }


@dataclass(slots=True)
class ThreadMessageView:
    id: str
    role: str
    content: str
    created_at: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "metadata": self.metadata.copy(),
        }


@dataclass(slots=True)
class ThreadRuntimeMessageView:
    role: str
    content: str

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ThreadRuntimeMessageView":
        return cls(
            role=str(record["role"]),
            content=str(record["content"]),
        )

    def to_record(self) -> dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
        }

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ThreadRuntimeMessageView):
            return self.role == other.role and self.content == other.content
        return False


@dataclass(slots=True)
class ThreadStatusSummaryView:
    id: str
    client_id: str
    status: str
    client_name: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "ThreadStatusSummaryView":
        return cls(
            id=str(record["id"]),
            client_id=str(record["client_id"]),
            status=str(record["status"]),
            client_name=record.get("client_name"),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "status": self.status,
            "client_name": self.client_name,
        }

