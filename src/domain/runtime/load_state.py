from dataclasses import dataclass, field
from typing import Mapping, cast

from src.domain.runtime.dialog_state import DialogState, merge_dialog_state
from src.domain.runtime.state_contracts import (
    ClientProfileState,
    KnowledgeChunkPayload,
    RuntimeMemoryEntry,
    RuntimeStatePatch,
)
from src.domain.runtime.value_parsing import coerce_int


UserMemoryByType = dict[str, list[RuntimeMemoryEntry]]
MemoryRecord = Mapping[str, object]


@dataclass(slots=True)
class LoadStateResult:
    conversation_summary: str | None = None
    history: list[Mapping[str, object]] = field(default_factory=list)
    client_id: str | None = None
    client_profile: ClientProfileState | None = None
    knowledge_chunks: list[KnowledgeChunkPayload] | None = None
    user_memory: UserMemoryByType = field(default_factory=dict)
    intent: str | None = None
    lifecycle: str | None = None
    cta: str | None = None
    decision: str | None = None
    dialog_state: DialogState | None = None
    topic: str | None = None
    lead_status: str | None = None
    repeat_count: int | None = None

    def to_state_patch(self) -> RuntimeStatePatch:
        result: RuntimeStatePatch = {
            "client_profile": self.client_profile,
            "conversation_summary": self.conversation_summary,
            "history": self.history,
            "knowledge_chunks": self.knowledge_chunks,
            "client_id": self.client_id,
            "user_memory": self.user_memory,
        }
        for field_name in (
            "intent",
            "lifecycle",
            "cta",
            "decision",
            "dialog_state",
            "topic",
            "lead_status",
            "repeat_count",
        ):
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        return result

    @staticmethod
    def build_memory_index(memories: list[MemoryRecord]) -> UserMemoryByType:
        memory_by_type: UserMemoryByType = {}
        for memory in memories:
            memory_type = str(memory["type"])
            memory_by_type.setdefault(memory_type, []).append(
                {"key": str(memory["key"]), "value": memory["value"]}
            )
        return memory_by_type

    def apply_system_memory(self, memories: list[MemoryRecord]) -> None:
        for memory in memories:
            if memory["type"] != "system":
                continue
            key = str(memory["key"])
            value = memory["value"]
            if key == "dialog_state" and isinstance(value, Mapping):
                self.dialog_state = merge_dialog_state(cast(Mapping[str, object], value), lifecycle=str(self.lifecycle or "cold"))
            elif key == "topic":
                self.topic = str(value) if value is not None else None
            elif key == "lead_status":
                self.lead_status = str(value) if value is not None else None
            elif key == "repeat_count":
                self.repeat_count = coerce_int(value, 0)
