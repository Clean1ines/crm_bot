from typing import Mapping, NotRequired, TypedDict


class RuntimeHistoryMessage(TypedDict):
    role: str
    content: str


class RuntimeMemoryEntry(TypedDict):
    key: str
    value: object


class RuntimeMemory(TypedDict, total=False):
    dialog_state: list[RuntimeMemoryEntry]
    system: list[RuntimeMemoryEntry]
    profile: list[RuntimeMemoryEntry]
    preferences: list[RuntimeMemoryEntry]


class KnowledgeChunkPayload(TypedDict):
    id: str
    score: float | None
    content: str


class RuntimeFeatures(TypedDict, total=False):
    topic: object
    risk: object
    urgency: object
    sentiment: object


class ToolResultPayload(TypedDict, total=False):
    ok: bool
    text: str
    ticket_id: str
    message_id: int
    payload: object


class ClientProfileState(TypedDict, total=False):
    id: str
    name: str
    email: str
    phone: str
    company: str


class ProjectIntegrationState(TypedDict, total=False):
    kind: str
    provider: str
    status: str
    config: Mapping[str, object]


class ProjectChannelState(TypedDict, total=False):
    kind: str
    provider: str
    status: str
    config: Mapping[str, object]


class ProjectRuntimeConfigurationState(TypedDict, total=False):
    settings: Mapping[str, object]
    policies: Mapping[str, object]
    limits: Mapping[str, object]
    integrations: list[ProjectIntegrationState]
    channels: list[ProjectChannelState]


class RuntimeStateInput(TypedDict, total=False):
    thread_id: str | None
    project_id: str | None
    client_id: str | None
    chat_id: int | str | None
    user_input: str
    response_text: str | None
    conversation_summary: str | None
    history: list[RuntimeHistoryMessage]
    user_memory: RuntimeMemory
    knowledge_chunks: list[KnowledgeChunkPayload]
    client_profile: ClientProfileState
    project_configuration: ProjectRuntimeConfigurationState
    decision: str
    intent: str | None
    lifecycle: str | None
    lead_status: str | None
    cta: str | None
    topic: str | None
    cta_hint: str | None
    emotion: str | None
    is_repeat_like: bool
    confidence: float | None
    requires_human: bool
    close_ticket: bool
    features: Mapping[str, object]
    dialog_state: object
    tool_name: str | None
    tool_args: Mapping[str, object]
    tool_result: object
    metadata: Mapping[str, object]
    messages: object


class RuntimeStatePatch(TypedDict, total=False):
    response_text: str
    metadata: Mapping[str, object]
    decision: str
    intent: str | None
    lifecycle: str
    lead_status: str
    cta: str
    topic: str
    cta_hint: str | None
    emotion: str
    is_repeat_like: bool
    confidence: float | None
    requires_human: bool
    features: Mapping[str, object]
    dialog_state: object
    tool_result: object

# Backward-compatible aliases for existing agent/runtime imports.
HistoryMessage = RuntimeHistoryMessage
UserMemoryEntry = RuntimeMemoryEntry
KnowledgeChunkState = KnowledgeChunkPayload
ToolArguments = Mapping[str, object]
ToolCallRecord = Mapping[str, object]
