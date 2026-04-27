from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from src.domain.runtime.state_contracts import (
    HistoryMessage,
    ProjectChannelState,
    ProjectIntegrationState,
    ProjectRuntimeConfigurationState,
)


def _object_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _project_integration_states(value: object) -> list[ProjectIntegrationState]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [
        cast(ProjectIntegrationState, item)
        for item in value
        if isinstance(item, Mapping)
    ]


def _project_channel_states(value: object) -> list[ProjectChannelState]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [
        cast(ProjectChannelState, item) for item in value if isinstance(item, Mapping)
    ]


@dataclass(slots=True)
class ProjectRuntimeContextDto:
    settings: dict[str, object] = field(default_factory=dict)
    policies: dict[str, object] = field(default_factory=dict)
    limits: dict[str, object] = field(default_factory=dict)
    integrations: list[ProjectIntegrationState] = field(default_factory=list)
    channels: list[ProjectChannelState] = field(default_factory=list)

    @classmethod
    def from_record(
        cls, record: dict[str, object] | None
    ) -> "ProjectRuntimeContextDto":
        payload = record or {}
        return cls(
            settings=_object_dict(payload.get("settings")),
            policies=_object_dict(payload.get("policies")),
            limits=_object_dict(payload.get("limits")),
            integrations=_project_integration_states(payload.get("integrations")),
            channels=_project_channel_states(payload.get("channels")),
        )

    def to_dict(self) -> ProjectRuntimeConfigurationState:
        return {
            "settings": dict(self.settings),
            "policies": dict(self.policies),
            "limits": dict(self.limits),
            "integrations": list(self.integrations),
            "channels": list(self.channels),
        }


@dataclass(slots=True)
class MessageProcessingOutcomeDto:
    text: str
    delivered: bool = False

    @classmethod
    def create(
        cls, text: str, *, delivered: bool = False
    ) -> "MessageProcessingOutcomeDto":
        return cls(text=text, delivered=delivered)


@dataclass(slots=True)
class GraphExecutionRequestDto:
    project_id: str
    thread_id: str
    chat_id: int
    question: str
    recent_history: list[HistoryMessage] = field(default_factory=list)
    runtime_context: ProjectRuntimeContextDto = field(
        default_factory=ProjectRuntimeContextDto
    )
    trace_id: str = ""


@dataclass(slots=True)
class GraphExecutionResultDto:
    response_text: str = ""
    delivered: bool = False

    @classmethod
    def from_graph_state(
        cls, state: Mapping[str, object] | None
    ) -> "GraphExecutionResultDto":
        payload = state or {}
        if payload.get("message_sent"):
            return cls(response_text="", delivered=True)
        response_text = payload.get("response_text")
        if response_text:
            return cls(response_text=str(response_text), delivered=False)
        return cls(response_text="", delivered=False)
