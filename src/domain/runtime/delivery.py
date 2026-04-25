from dataclasses import dataclass
from typing import Mapping, cast

from src.domain.runtime.state_contracts import RuntimeStateInput, RuntimeStatePatch, ToolResultPayload


@dataclass(slots=True)
class ResponseDeliveryContext:
    chat_id: int | str | None
    project_id: str | None = None
    thread_id: str | None = None
    response_text: str | None = None
    tool_result: ToolResultPayload | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "ResponseDeliveryContext":
        raw_tool_result = state.get("tool_result")
        tool_result = cast(ToolResultPayload, raw_tool_result) if isinstance(raw_tool_result, Mapping) else None
        return cls(
            chat_id=state.get("chat_id"),
            project_id=state.get("project_id"),
            thread_id=state.get("thread_id"),
            response_text=state.get("response_text"),
            tool_result=tool_result,
        )

    def resolve_response_text(self) -> str:
        if self.tool_result and self.tool_result.get("text"):
            return str(self.tool_result["text"])
        if self.response_text:
            return str(self.response_text)
        return "Sorry, I could not prepare a response."


@dataclass(slots=True)
class ResponseDeliveryResult:
    message_sent: bool
    response_text: str | None = None
    requires_human: bool = False

    def to_state_patch(self) -> RuntimeStatePatch:
        result: RuntimeStatePatch = {
            "message_sent": self.message_sent,
            "response_text": self.response_text,
        }
        if self.requires_human:
            result["requires_human"] = True
        return result
