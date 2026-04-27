from dataclasses import asdict, dataclass, field

from src.domain.runtime.state_contracts import (
    HistoryMessage,
    ProjectChannelState,
    ProjectIntegrationState,
    ProjectRuntimeConfigurationState,
)


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
            settings=dict(payload.get("settings") or {}),
            policies=dict(payload.get("policies") or {}),
            limits=dict(payload.get("limits") or {}),
            integrations=list(payload.get("integrations") or []),
            channels=list(payload.get("channels") or []),
        )

    def to_dict(self) -> ProjectRuntimeConfigurationState:
        return ProjectRuntimeConfigurationState(**asdict(self))


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
        cls, state: dict[str, object] | None
    ) -> "GraphExecutionResultDto":
        payload = state or {}
        if payload.get("message_sent"):
            return cls(response_text="", delivered=True)
        response_text = payload.get("response_text")
        if response_text:
            return cls(response_text=str(response_text), delivered=False)
        return cls(response_text="", delivered=False)
