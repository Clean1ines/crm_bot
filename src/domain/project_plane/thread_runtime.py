from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ThreadRuntimeSnapshot:
    thread_id: str
    client_id: str | None = None
    project_id: str | None = None
    status: str | None = None
    context_summary: str | None = None
    manager_user_id: str | None = None
    manager_chat_id: str | None = None
    chat_id: int | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any] | None) -> "ThreadRuntimeSnapshot | None":
        if not record:
            return None
        return cls(
            thread_id=str(record.get("id") or ""),
            client_id=str(record["client_id"]) if record.get("client_id") is not None else None,
            project_id=str(record["project_id"]) if record.get("project_id") is not None else None,
            status=record.get("status"),
            context_summary=record.get("context_summary"),
            manager_user_id=(
                str(record["manager_user_id"]) if record.get("manager_user_id") is not None else None
            ),
            manager_chat_id=(
                str(record["manager_chat_id"]) if record.get("manager_chat_id") is not None else None
            ),
            chat_id=record.get("chat_id"),
        )


@dataclass(slots=True)
class ThreadAnalyticsSnapshot:
    intent: str | None = None
    lifecycle: str | None = None
    cta: str | None = None
    decision: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any] | None) -> "ThreadAnalyticsSnapshot":
        payload = record or {}
        return cls(
            intent=payload.get("intent"),
            lifecycle=payload.get("lifecycle"),
            cta=payload.get("cta"),
            decision=payload.get("decision"),
        )

    def to_state_patch(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.intent is not None:
            result["intent"] = self.intent
        if self.lifecycle is not None:
            result["lifecycle"] = self.lifecycle
        if self.cta is not None:
            result["cta"] = self.cta
        if self.decision is not None:
            result["decision"] = self.decision
        return result
