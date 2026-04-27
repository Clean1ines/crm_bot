from dataclasses import dataclass
from typing import Mapping, cast

from src.domain.runtime.dialog_state import (
    DialogState,
    dialog_state_from_memory,
    merge_dialog_state,
)
from src.domain.runtime.state_contracts import (
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
    ToolArguments,
)
from src.domain.runtime.value_parsing import coerce_bool, coerce_int


def infer_topic_from_intent(intent: str | None) -> str | None:
    value = (intent or "").strip().lower()
    mapping = {
        "ask_price": "pricing",
        "ask_features": "product",
        "ask_integration": "integration",
        "pricing": "pricing",
        "sales": "product",
        "support": "support",
        "feedback": "feedback",
        "handoff_request": "handoff",
        "angry": "angry",
    }
    return mapping.get(value)


def extract_dialog_state_from_memory(user_memory: RuntimeMemory | None) -> DialogState:
    return dialog_state_from_memory(user_memory, lifecycle="active_client")


@dataclass(slots=True)
class PersistenceContext:
    thread_id: str | None
    project_id: str | None
    response_text: str | None
    user_input: str
    client_id: str | None
    close_ticket: bool
    intent: str | None = None
    lifecycle: str | None = None
    cta: str | None = None
    decision: str | None = None
    confidence: float | None = None
    requires_human: bool = False
    tool_name: str | None = None
    tool_args: ToolArguments | None = None
    tool_result: object | None = None
    dialog_state: DialogState | None = None
    lead_status: str | None = None
    state_payload: RuntimeStatePatch | None = None
    user_memory: RuntimeMemory | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "PersistenceContext":
        state_copy: RuntimeStatePatch = {}
        if "thread_id" in state:
            state_copy["thread_id"] = state["thread_id"]
        if "project_id" in state:
            state_copy["project_id"] = state["project_id"]
        if "client_id" in state:
            state_copy["client_id"] = state["client_id"]
        if "response_text" in state:
            state_copy["response_text"] = state["response_text"]
        if "metadata" in state:
            state_copy["metadata"] = state["metadata"]
        if "decision" in state:
            state_copy["decision"] = state["decision"]
        if "intent" in state:
            state_copy["intent"] = state["intent"]
        if "lifecycle" in state:
            state_copy["lifecycle"] = state["lifecycle"]
        if "lead_status" in state:
            state_copy["lead_status"] = state["lead_status"]
        if "cta" in state:
            state_copy["cta"] = state["cta"]
        if "topic" in state:
            state_copy["topic"] = state["topic"]
        if "cta_hint" in state:
            state_copy["cta_hint"] = state["cta_hint"]
        if "emotion" in state:
            emotion = state["emotion"]
            if emotion is not None:
                state_copy["emotion"] = emotion
        if "is_repeat_like" in state:
            state_copy["is_repeat_like"] = state["is_repeat_like"]
        if "confidence" in state:
            state_copy["confidence"] = state["confidence"]
        if "requires_human" in state:
            state_copy["requires_human"] = state["requires_human"]
        if "close_ticket" in state:
            state_copy["close_ticket"] = state["close_ticket"]
        if "features" in state:
            state_copy["features"] = state["features"]
        if "dialog_state" in state:
            state_copy["dialog_state"] = state["dialog_state"]
        if "tool_name" in state:
            state_copy["tool_name"] = state["tool_name"]
        if "tool_args" in state:
            state_copy["tool_args"] = state["tool_args"]
        if "tool_result" in state:
            state_copy["tool_result"] = state["tool_result"]

        raw_dialog_state = state.get("dialog_state")
        dialog_state = raw_dialog_state if isinstance(raw_dialog_state, dict) else None

        raw_tool_args = state.get("tool_args")
        tool_args = raw_tool_args if isinstance(raw_tool_args, Mapping) else None

        return cls(
            thread_id=state.get("thread_id"),
            project_id=state.get("project_id"),
            response_text=state.get("response_text"),
            user_input=str(state.get("user_input") or "").lower(),
            client_id=state.get("client_id"),
            close_ticket=coerce_bool(state.get("close_ticket"), False),
            intent=state.get("intent"),
            lifecycle=state.get("lifecycle"),
            cta=state.get("cta"),
            decision=state.get("decision"),
            confidence=state.get("confidence"),
            requires_human=coerce_bool(state.get("requires_human"), False),
            tool_name=state.get("tool_name"),
            tool_args=dict(tool_args) if tool_args is not None else None,
            tool_result=state.get("tool_result"),
            dialog_state=cast(DialogState | None, dialog_state),
            lead_status=state.get("lead_status"),
            state_payload=state_copy,
            user_memory=state.get("user_memory"),
        )

    def normalized_dialog_state(self) -> DialogState:
        fallback_lifecycle = self._fallback_lifecycle()
        existing = merge_dialog_state(self.dialog_state, lifecycle=fallback_lifecycle)
        dialog_state = self._dialog_state_from_existing(existing)
        memory_dialog_state = dialog_state_from_memory(
            self.user_memory, lifecycle=fallback_lifecycle
        )

        merged: dict[str, object] = dict(memory_dialog_state)
        merged.update(dialog_state)
        return merge_dialog_state(merged, lifecycle=fallback_lifecycle)

    def _fallback_lifecycle(self) -> str:
        return str(self.lifecycle or self.lead_status or "active_client")

    def _dialog_state_from_existing(self, existing: DialogState) -> DialogState:
        dialog_state: DialogState = {
            "last_intent": existing.get("last_intent") or self.intent,
            "last_cta": existing.get("last_cta") or self.cta,
            "last_topic": existing.get("last_topic")
            or infer_topic_from_intent(self.intent),
            "repeat_count": coerce_int(existing.get("repeat_count"), 0),
            "lead_status": self._lead_status(existing),
            "lifecycle": self._lifecycle(existing),
        }
        return _ensure_repeat_count(dialog_state)

    def _lead_status(self, existing: DialogState) -> str:
        return (
            existing.get("lead_status")
            or self.lead_status
            or self.lifecycle
            or "active_client"
        )

    def _lifecycle(self, existing: DialogState) -> str:
        return (
            self.lifecycle
            or existing.get("lifecycle")
            or self.lead_status
            or "active_client"
        )


def _ensure_repeat_count(dialog_state: DialogState) -> DialogState:
    if dialog_state["repeat_count"] <= 0 and dialog_state["last_intent"]:
        dialog_state["repeat_count"] = 1

    return dialog_state
