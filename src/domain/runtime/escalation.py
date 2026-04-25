from dataclasses import dataclass
from typing import Mapping, cast

from src.domain.runtime.state_contracts import (
    ClientProfileState,
    RuntimeStateInput,
    RuntimeStatePatch,
    ToolResultPayload,
)


@dataclass(slots=True)
class EscalationContext:
    thread_id: str | None
    project_id: str | None
    user_input: str = ""
    client_id: str | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "EscalationContext":
        client_id = None
        client_profile = state.get("client_profile")
        if isinstance(client_profile, Mapping):
            profile = cast(ClientProfileState, client_profile)
            client_id = profile.get("id")
        return cls(
            thread_id=state.get("thread_id"),
            project_id=state.get("project_id"),
            user_input=str(state.get("user_input") or ""),
            client_id=client_id,
        )

    def ticket_payload(self) -> Mapping[str, object]:
        return {
            "title": "Escalation: user requested human help",
            "description": f"User message: {self.user_input[:500]}",
            "priority": "normal",
        }

    def notification_payload(self) -> Mapping[str, object]:
        return {
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "message": self.user_input[:200],
        }


@dataclass(slots=True)
class EscalationResult:
    requires_human: bool = True
    response_text: str = "Your request has been handed off to a manager. Please wait for a reply."
    tool_result: ToolResultPayload | object | None = None

    def to_state_patch(self) -> RuntimeStatePatch:
        return {
            "requires_human": self.requires_human,
            "response_text": self.response_text,
            "tool_result": self.tool_result,
        }
