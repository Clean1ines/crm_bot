from dataclasses import dataclass, field
from typing import Mapping, cast

from src.domain.runtime.dialog_state import DialogState, default_dialog_state, dialog_state_from_memory, merge_dialog_state
from src.domain.runtime.state_contracts import RuntimeFeatures, RuntimeStateInput, RuntimeStatePatch


@dataclass(slots=True)
class PolicyDecisionContext:
    lifecycle: str = "cold"
    intent: str | None = None
    features: RuntimeFeatures | None = None
    dialog_state: DialogState = field(default_factory=default_dialog_state)
    thread_id: str | None = None
    project_id: str | None = None
    confidence: float | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "PolicyDecisionContext":
        raw_dialog_state = state.get("dialog_state")
        if isinstance(raw_dialog_state, Mapping):
            dialog_state = merge_dialog_state(cast(Mapping[str, object], raw_dialog_state))
        else:
            dialog_state = dialog_state_from_memory(state.get("user_memory"))

        return cls(
            lifecycle=str(state.get("lifecycle") or "cold"),
            intent=state.get("intent"),
            features=state.get("features"),
            dialog_state=dialog_state,
            thread_id=state.get("thread_id"),
            project_id=state.get("project_id"),
            confidence=state.get("confidence"),
        )


@dataclass(slots=True)
class PolicyDecisionResult:
    lifecycle: str
    decision: str
    cta: str
    topic: str
    lead_status: str
    dialog_state: DialogState

    def to_state_patch(self, *, previous_lifecycle: str) -> RuntimeStatePatch:
        result: RuntimeStatePatch = {
            "decision": self.decision,
            "cta": self.cta,
            "topic": self.topic,
            "lead_status": self.lead_status,
            "dialog_state": self.dialog_state,
        }
        if self.lifecycle != previous_lifecycle:
            result["lifecycle"] = self.lifecycle
        return result

    def to_event_payload(self, *, confidence: float | None) -> RuntimeStatePatch:
        return {
            "decision": self.decision,
            "intent": self.dialog_state.get("last_intent"),
            "lifecycle": self.lifecycle,
            "cta": self.cta,
            "topic": self.topic,
            "repeat_count": self.dialog_state.get("repeat_count"),
            "lead_status": self.lead_status,
            "confidence": confidence,
        }
