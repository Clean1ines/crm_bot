from dataclasses import dataclass
from typing import Mapping

from src.domain.runtime.state_contracts import RuntimeStateInput, RuntimeStatePatch, ToolArguments, ToolResultPayload


@dataclass(slots=True)
class ToolExecutionContext:
    tool_name: str | None
    tool_args: ToolArguments
    project_id: str | None = None
    thread_id: str | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "ToolExecutionContext":
        raw_args = state.get("tool_args")
        return cls(
            tool_name=state.get("tool_name"),
            tool_args=dict(raw_args) if isinstance(raw_args, Mapping) else {},
            project_id=state.get("project_id"),
            thread_id=state.get("thread_id"),
        )

    def execution_context(self) -> RuntimeStatePatch:
        return {
            "project_id": self.project_id,
            "thread_id": self.thread_id,
        }


@dataclass(slots=True)
class ToolExecutionResult:
    tool_result: ToolResultPayload | object | None = None
    requires_human: bool = False
    response_text: str | None = None

    def to_state_patch(self) -> RuntimeStatePatch:
        result: RuntimeStatePatch = {
            "tool_result": self.tool_result,
            "requires_human": self.requires_human,
        }
        if self.response_text is not None:
            result["response_text"] = self.response_text
        return result
