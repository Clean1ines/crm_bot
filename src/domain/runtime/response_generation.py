from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Mapping, cast

from src.domain.runtime.cta import normalize_cta
from src.domain.runtime.dialog_state import DialogState
from src.domain.runtime.state_contracts import (
    KnowledgeChunkPayload,
    ProjectRuntimeConfigurationState,
    RuntimeFeatures,
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
)

Answerability = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "conflicting_evidence",
]
RetrievalStatus = Literal["retrieved", "empty", "failed", "skipped", "unknown"]


class GenerationMode(StrEnum):
    KNOWLEDGE_ANSWER = "KNOWLEDGE_ANSWER"
    TOOL_RESULT_RESPONSE = "TOOL_RESULT_RESPONSE"
    CONVERSATIONAL_RESPONSE = "CONVERSATIONAL_RESPONSE"


GenerationParseStatus = Literal["valid", "invalid_json", "invalid_schema", "not_called"]
GenerationSchemaStatus = Literal[
    "valid",
    "invalid_enum",
    "invalid_payload",
    "missing_required_answer",
    "invalid_answerability_contract",
    "not_called",
]
EvidenceReferenceStatus = Literal[
    "valid",
    "missing_required_refs",
    "unknown_refs",
    "invalid_for_answerability",
    "not_applicable",
    "not_called",
]
SemanticGroundingStatus = Literal[
    "unchecked",
    "failed",
    "not_applicable",
]

ANSWERABILITY_VALUES = frozenset(
    {
        "supported",
        "partially_supported",
        "unsupported",
        "conflicting_evidence",
    }
)
GENERATION_MODE_VALUES = frozenset(item.value for item in GenerationMode)
RETRIEVAL_STATUS_VALUES = frozenset(
    {"retrieved", "empty", "failed", "skipped", "unknown"}
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
    topic: str = ""
    turn_relation: str = ""
    generation_mode: GenerationMode | None = None
    tool_result: object | None = None
    tool_execution_status: str | None = None
    tool_response_text: str | None = None
    knowledge_retrieval_status: RetrievalStatus = "unknown"
    knowledge_retrieval_error_type: str | None = None

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
            cta=normalize_cta(state.get("cta")) or "",
            topic=str(state.get("topic") or ""),
            turn_relation=str(state.get("turn_relation") or ""),
            generation_mode=_generation_mode_from_state(state),
            tool_result=state.get("tool_result"),
            tool_execution_status=_text_or_none(state.get("tool_execution_status")),
            tool_response_text=_text_or_none(state.get("tool_response_text")),
            knowledge_retrieval_status=_retrieval_status_from_state(
                state.get("knowledge_retrieval_status")
            ),
            knowledge_retrieval_error_type=_text_or_none(
                state.get("knowledge_retrieval_error_type")
            ),
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
            "generation_mode": self.generation_mode,
            "tool_result": self.tool_result,
            "tool_execution_status": self.tool_execution_status,
            "tool_response_text": self.tool_response_text,
        }


@dataclass(slots=True)
class ResponseGenerationResult:
    response_text: str
    metadata: Mapping[str, object] = field(default_factory=dict)
    cta: str | None = None
    topic: str | None = None

    def to_state_patch(self) -> RuntimeStatePatch:
        patch: RuntimeStatePatch = {
            "response_text": self.response_text,
            "metadata": self.metadata,
        }
        if self.cta is not None:
            patch["cta"] = self.cta
        if self.topic is not None:
            patch["topic"] = self.topic
        return patch


@dataclass(frozen=True, slots=True)
class StructuredResponseResult:
    answerability: Answerability
    answer: str | None = None
    supporting_evidence_refs: list[str] = field(default_factory=list)
    supporting_entry_ids: list[str] = field(default_factory=list)
    unsupported_aspects: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "StructuredResponseResult":
        if "supporting_entry_ids" in payload:
            raise ValueError("legacy supporting_entry_ids field is forbidden")
        raw_answerability = str(payload.get("answerability") or "").strip().lower()
        if raw_answerability not in ANSWERABILITY_VALUES:
            raise ValueError("invalid answerability")

        raw_answer = payload.get("answer")
        answer = str(raw_answer).strip() if raw_answer is not None else None
        if answer == "":
            answer = None

        return cls(
            answerability=cast(Answerability, raw_answerability),
            answer=answer,
            supporting_evidence_refs=_strict_string_list(
                payload.get("supporting_evidence_refs")
            ),
            unsupported_aspects=_string_list(payload.get("unsupported_aspects")),
        )

    def with_resolved_entry_ids(
        self,
        entry_ids: list[str],
    ) -> "StructuredResponseResult":
        return StructuredResponseResult(
            answerability=self.answerability,
            answer=self.answer,
            supporting_evidence_refs=list(self.supporting_evidence_refs),
            supporting_entry_ids=list(entry_ids),
            unsupported_aspects=list(self.unsupported_aspects),
        )

    def metadata(self) -> dict[str, object]:
        return {
            "answerability": self.answerability,
            "answer": self.answer,
            "supporting_evidence_refs": list(self.supporting_evidence_refs),
            "supporting_entry_ids": list(self.supporting_entry_ids),
            "unsupported_aspects": list(self.unsupported_aspects),
        }


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


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _retrieval_status_from_state(value: object) -> RetrievalStatus:
    text = str(value or "unknown").strip().lower()
    if text in RETRIEVAL_STATUS_VALUES:
        return cast(RetrievalStatus, text)
    return "unknown"


def normalize_generation_mode(value: object) -> GenerationMode | None:
    raw_mode = str(value or "").strip().upper()
    for mode in GenerationMode:
        if raw_mode == mode.value:
            return mode
    return None


def _generation_mode_from_state(state: RuntimeStateInput) -> GenerationMode | None:
    return normalize_generation_mode(state.get("generation_mode"))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text_or_none(item)
        if text:
            result.append(text)
    return result


def _strict_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("invalid supporting_evidence_refs")
        text = item.strip()
        if not text:
            raise ValueError("invalid supporting_evidence_refs")
        result.append(text)
    return result


def _mapping_list_or_empty(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []

    result: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(item)
    return result
