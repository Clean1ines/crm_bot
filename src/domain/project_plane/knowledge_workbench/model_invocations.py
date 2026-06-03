from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .shared import (
    DocumentId,
    DomainInvariantError,
    ModelInvocationId,
    NodeRunId,
    ProcessingRunId,
    ProjectId,
    require_document_id,
    require_node_run_id,
    require_processing_run_id,
    require_project_id,
)


class ModelProvider(StrEnum):
    GROQ = "groq"


class ModelInvocationStatus(StrEnum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    REQUEST_TOO_LARGE = "request_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    PROVIDER_ERROR = "provider_error"
    NETWORK_ERROR = "network_error"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ModelInvocation:
    invocation_id: ModelInvocationId
    node_run_id: NodeRunId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    provider: ModelProvider
    model: str
    api_key_slot: str
    route_chain: tuple[str, ...]
    attempt_index: int
    status: ModelInvocationStatus
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_kind: str | None = None
    cooldown_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.invocation_id:
            raise DomainInvariantError("invocation_id is required")
        require_node_run_id(self.node_run_id)
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.model:
            raise DomainInvariantError("model is required")
        if not self.api_key_slot:
            raise DomainInvariantError("api_key_slot is required")
        if self.attempt_index < 0:
            raise DomainInvariantError("attempt_index must be non-negative")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise DomainInvariantError(
                "total_tokens must equal prompt + completion tokens"
            )
