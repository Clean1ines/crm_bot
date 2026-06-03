from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .shared import (
    ArtifactId,
    DocumentId,
    DomainInvariantError,
    JsonValue,
    NodeRunId,
    ProcessingRunId,
    ProjectId,
    SectionId,
    require_document_id,
    require_node_run_id,
    require_processing_run_id,
    require_project_id,
)


class ProcessingNodeName(StrEnum):
    INITIALIZE_REGISTRY = "initialize_registry"
    RESTORE_CHECKPOINT = "restore_checkpoint"
    FAQ_SURFACE_SECTION_FINDINGS = "faq_surface_claim_observations"
    DETERMINISTIC_DEDUP = "deterministic_dedup"
    FAQ_SURFACE_REGISTRY_MERGE = "faq_surface_registry_merge"
    REGISTRY_UPDATE_APPLICATION = "registry_update_application"
    REGISTRY_SNAPSHOT = "registry_snapshot"
    FAQ_SURFACE_FINAL_RECONCILIATION = "faq_surface_final_reconciliation"
    SURFACE_MATERIALIZATION = "surface_materialization"
    MODEL_ROUTE = "model_route"
    PROCESS_PARALLEL_SECTION_BATCH = "process_parallel_section_batch"


class ProcessingNodeKind(StrEnum):
    LLM_PROMPT = "llm_prompt"
    DETERMINISTIC_CODE = "deterministic_code"
    PERSISTENCE = "persistence"
    MATERIALIZATION = "materialization"
    MODEL_ROUTER = "model_router"
    CONTROL_FLOW = "control_flow"


class ProcessingNodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ProcessingNodeArtifactType(StrEnum):
    INPUT_SNAPSHOT = "input_snapshot"
    RAW_LLM_OUTPUT = "raw_llm_output"
    PARSED_LLM_OUTPUT = "parsed_llm_output"
    DETERMINISTIC_RESULT = "deterministic_result"
    APPLIED_RESULT = "applied_result"
    REGISTRY_SNAPSHOT = "registry_snapshot"
    ERROR_REPORT = "error_report"


@dataclass(frozen=True, slots=True)
class ProcessingNodeRun:
    node_run_id: NodeRunId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    node_name: ProcessingNodeName
    node_kind: ProcessingNodeKind
    status: ProcessingNodeStatus
    section_id: SectionId | None = None
    input_snapshot_id: ArtifactId | None = None
    output_snapshot_id: ArtifactId | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    model_name: str | None = None
    model_provider: str | None = None
    groq_key_slot: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error_kind: str | None = None
    error_message_user: str | None = None
    error_message_internal: str | None = None

    def __post_init__(self) -> None:
        require_node_run_id(self.node_run_id)
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise DomainInvariantError(
                "node total_tokens must equal prompt + completion tokens"
            )
        if self.node_kind is ProcessingNodeKind.LLM_PROMPT and self.model_name is None:
            raise DomainInvariantError("LLM prompt node must record model_name")


@dataclass(frozen=True, slots=True)
class ProcessingNodeArtifact:
    artifact_id: ArtifactId
    node_run_id: NodeRunId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    artifact_type: ProcessingNodeArtifactType
    payload_json: JsonValue
    schema_version: int
    created_at: datetime | None = None
    section_id: SectionId | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise DomainInvariantError("artifact_id is required")
        require_node_run_id(self.node_run_id)
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if self.schema_version < 1:
            raise DomainInvariantError("schema_version must be positive")
