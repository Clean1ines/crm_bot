from dataclasses import dataclass
from datetime import datetime
from typing import Any


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
    def from_record(cls, record: dict[str, Any] | None) -> "ThreadWithProjectView | None":
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

    def to_record(self) -> dict[str, Any]:
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
    def from_record(cls, record: dict[str, Any] | None) -> "ThreadAnalyticsView | None":
        if not record:
            return None
        return cls(
            intent=record.get("intent"),
            lifecycle=record.get("lifecycle"),
            cta=record.get("cta"),
            decision=record.get("decision"),
        )

    def to_record(self) -> dict[str, Any]:
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
    def from_record(cls, record: dict[str, Any] | None) -> "ThreadMessageCounts":
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
