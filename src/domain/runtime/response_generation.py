from dataclasses import dataclass, field
from typing import Mapping, cast

from src.domain.runtime.dialog_state import DialogState
from src.domain.runtime.state_contracts import (
    KnowledgeChunkPayload,
    ProjectRuntimeConfigurationState,
    RuntimeFeatures,
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
)


@dataclass(slots=True)
class ResponseGenerationContext:
    decision: str = "LLM_GENERATE"
    user_input: str = ""
    conversation_summary: str | None = None
    history: list[Mapping[str, object]] = field(default_factory=list)
    knowledge_chunks: list[KnowledgeChunkPayload] = field(default_factory=list)
    user_memory: RuntimeMemory | None = None
    dialog_state: DialogState | None = None
    features: RuntimeFeatures | Mapping[str, object] | None = None
    project_configuration: ProjectRuntimeConfigurationState | None = None
    intent: str = ""
    lifecycle: str = ""
    cta: str = ""

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "ResponseGenerationContext":
        return cls(
            decision=str(state.get("decision") or "LLM_GENERATE"),
            user_input=str(state.get("user_input") or ""),
            conversation_summary=state.get("conversation_summary"),
            history=list(state.get("history") or []),
            knowledge_chunks=list(state.get("knowledge_chunks") or []),
            user_memory=state.get("user_memory"),
            dialog_state=_dialog_state_or_none(state.get("dialog_state")),
            features=_mapping_or_none(state.get("features")),
            project_configuration=_project_configuration_or_none(
                state.get("project_configuration")
            ),
            intent=str(state.get("intent") or ""),
            lifecycle=str(state.get("lifecycle") or ""),
            cta=str(state.get("cta") or ""),
        )

    def prompt_payload(self) -> Mapping[str, object]:
        return {
            "decision": self.decision,
            "user_input": self.user_input,
            "conversation_summary": self.conversation_summary,
            "history": self.history,
            "knowledge_chunks": self.knowledge_chunks,
            "user_memory": self.user_memory,
            "features": self.features,
            "project_configuration": self.project_configuration,
        }


@dataclass(slots=True)
class ResponseGenerationResult:
    response_text: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_state_patch(self) -> RuntimeStatePatch:
        return {"response_text": self.response_text, "metadata": self.metadata}


def _dialog_state_or_none(value: object) -> DialogState | None:
    if not isinstance(value, Mapping):
        return None
    return cast(DialogState, value)


def _mapping_or_none(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return value


def _project_configuration_or_none(
    value: object,
) -> ProjectRuntimeConfigurationState | None:
    mapping = _mapping_or_none(value)
    if mapping is None:
        return None
    return cast(ProjectRuntimeConfigurationState, mapping)
