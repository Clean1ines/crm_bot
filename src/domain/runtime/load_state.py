from dataclasses import dataclass, field
from typing import Callable, Mapping, cast

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
        if self.intent is not None:
            result["intent"] = self.intent
        if self.lifecycle is not None:
            result["lifecycle"] = self.lifecycle
        if self.cta is not None:
            result["cta"] = self.cta
        if self.decision is not None:
            result["decision"] = self.decision
        if self.dialog_state is not None:
            result["dialog_state"] = self.dialog_state
        if self.topic is not None:
            result["topic"] = self.topic
        if self.lead_status is not None:
            result["lead_status"] = self.lead_status
        if self.repeat_count is not None:
            result["repeat_count"] = self.repeat_count
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
        handlers = self._system_memory_handlers()
        for memory in memories:
            if not _is_system_memory(memory):
                continue

            handler = handlers.get(str(memory["key"]))
            if handler is not None:
                handler(memory["value"])

    def _system_memory_handlers(self) -> Mapping[str, "SystemMemoryHandler"]:
        return {
            "dialog_state": self._apply_dialog_state_memory,
            "topic": self._apply_topic_memory,
            "lead_status": self._apply_lead_status_memory,
            "repeat_count": self._apply_repeat_count_memory,
        }

    def _apply_dialog_state_memory(self, value: object) -> None:
        if not isinstance(value, Mapping):
            return

        self.dialog_state = merge_dialog_state(
            cast(Mapping[str, object], value),
            lifecycle=str(self.lifecycle or "cold"),
        )

    def _apply_topic_memory(self, value: object) -> None:
        self.topic = _optional_text(value)

    def _apply_lead_status_memory(self, value: object) -> None:
        self.lead_status = _optional_text(value)

    def _apply_repeat_count_memory(self, value: object) -> None:
        self.repeat_count = coerce_int(value, 0)


SystemMemoryHandler = Callable[[object], None]


def _is_system_memory(memory: MemoryRecord) -> bool:
    return memory["type"] == "system"


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None
