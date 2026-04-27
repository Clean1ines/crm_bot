from dataclasses import dataclass

from src.domain.project_plane.json_types import JsonValue


RuntimeRecord = dict[str, JsonValue]


def _optional_str(value: JsonValue) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


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
    def from_record(cls, record: RuntimeRecord | None) -> "ThreadRuntimeSnapshot | None":
        if not record:
            return None
        return cls(
            thread_id=str(record.get("id") or ""),
            client_id=_optional_str(record.get("client_id")),
            project_id=_optional_str(record.get("project_id")),
            status=_optional_str(record.get("status")),
            context_summary=_optional_str(record.get("context_summary")),
            manager_user_id=_optional_str(record.get("manager_user_id")),
            manager_chat_id=_optional_str(record.get("manager_chat_id")),
            chat_id=_optional_int(record.get("chat_id")),
        )


@dataclass(slots=True)
class ThreadAnalyticsSnapshot:
    intent: str | None = None
    lifecycle: str | None = None
    cta: str | None = None
    decision: str | None = None

    @classmethod
    def from_record(cls, record: RuntimeRecord | None) -> "ThreadAnalyticsSnapshot":
        payload = record or {}
        return cls(
            intent=_optional_str(payload.get("intent")),
            lifecycle=_optional_str(payload.get("lifecycle")),
            cta=_optional_str(payload.get("cta")),
            decision=_optional_str(payload.get("decision")),
        )

    def to_state_patch(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.intent is not None:
            result["intent"] = self.intent
        if self.lifecycle is not None:
            result["lifecycle"] = self.lifecycle
        if self.cta is not None:
            result["cta"] = self.cta
        if self.decision is not None:
            result["decision"] = self.decision
        return result
