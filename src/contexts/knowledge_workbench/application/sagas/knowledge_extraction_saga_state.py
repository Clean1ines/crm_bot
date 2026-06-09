from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class KnowledgeExtractionWorkflowStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_FOR_EXTERNAL_EVENT = "WAITING_FOR_EXTERNAL_EVENT"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class KnowledgeExtractionPhaseKey(StrEnum):
    DOCUMENT_ACCEPTED = "DOCUMENT_ACCEPTED"
    SOURCE_DOCUMENT_PERSISTED = "SOURCE_DOCUMENT_PERSISTED"
    SOURCE_UNITS_CREATED = "SOURCE_UNITS_CREATED"
    PROMPT_A_WORK_SCHEDULED = "PROMPT_A_WORK_SCHEDULED"
    PROMPT_A_WORK_COMPLETED = "PROMPT_A_WORK_COMPLETED"
    PROMPT_A_ARTIFACTS_APPLIED = "PROMPT_A_ARTIFACTS_APPLIED"
    DRAFT_EMBEDDINGS_BUILT = "DRAFT_EMBEDDINGS_BUILT"
    DRAFT_CLUSTERS_BUILT = "DRAFT_CLUSTERS_BUILT"
    PROMPT_B_WORK_SCHEDULED = "PROMPT_B_WORK_SCHEDULED"
    PROMPT_B_WORK_COMPLETED = "PROMPT_B_WORK_COMPLETED"
    FINAL_KNOWLEDGE_PREPARED = "FINAL_KNOWLEDGE_PREPARED"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    PUBLISHED = "PUBLISHED"
    RETRIEVAL_EMBEDDINGS_BUILT = "RETRIEVAL_EMBEDDINGS_BUILT"
    INTERMEDIATE_ARTIFACTS_CLEANED = "INTERMEDIATE_ARTIFACTS_CLEANED"
    DONE = "DONE"


class KnowledgeExtractionPhaseStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionPhaseCheckpoint:
    workflow_run_id: str
    phase_key: KnowledgeExtractionPhaseKey
    phase_status: KnowledgeExtractionPhaseStatus
    expected_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    idempotency_key: str = ""
    last_event_ref: str | None = None
    checkpoint_payload: Mapping[str, object] = field(default_factory=dict)
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_negative(self.expected_count, "expected_count")
        _require_non_negative(self.completed_count, "completed_count")
        _require_non_negative(self.failed_count, "failed_count")
        _require_non_negative(self.blocked_count, "blocked_count")

        if self.expected_count != 0:
            recorded_count = (
                self.completed_count + self.failed_count + self.blocked_count
            )
            if recorded_count > self.expected_count:
                raise ValueError(
                    "completed_count + failed_count + blocked_count "
                    "must be <= expected_count",
                )

        object.__setattr__(
            self,
            "checkpoint_payload",
            MappingProxyType(dict(self.checkpoint_payload)),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionWorkflowState:
    workflow_run_id: str
    project_id: str
    source_document_ref: str
    status: KnowledgeExtractionWorkflowStatus
    current_phase: KnowledgeExtractionPhaseKey
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...] = ()
    pause_reason: str | None = None
    failure_kind: str | None = None
    failure_message: str | None = None
    review_status: str | None = None
    publication_ref: str | None = None
    cleanup_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.project_id, "project_id")
        _require_non_empty(self.source_document_ref, "source_document_ref")

        seen_phase_keys: set[KnowledgeExtractionPhaseKey] = set()
        for checkpoint in self.checkpoints:
            if checkpoint.workflow_run_id != self.workflow_run_id:
                raise ValueError(
                    "checkpoint workflow_run_id must match workflow state",
                )
            if checkpoint.phase_key in seen_phase_keys:
                raise ValueError("duplicate phase checkpoint")
            seen_phase_keys.add(checkpoint.phase_key)

        if (
            self.status is KnowledgeExtractionWorkflowStatus.COMPLETED
            and self.completed_at is None
        ):
            raise ValueError("completed workflow state requires completed_at")
        if (
            self.status is KnowledgeExtractionWorkflowStatus.CANCELLED
            and self.cancelled_at is None
        ):
            raise ValueError("cancelled workflow state requires cancelled_at")
        if self.status is KnowledgeExtractionWorkflowStatus.FAILED:
            _require_non_empty(self.failure_kind, "failure_kind")
        if (
            self.status is KnowledgeExtractionWorkflowStatus.WAITING_FOR_REVIEW
            and self.current_phase is not KnowledgeExtractionPhaseKey.WAITING_FOR_REVIEW
        ):
            raise ValueError(
                "WAITING_FOR_REVIEW workflow status requires WAITING_FOR_REVIEW phase",
            )


def _require_non_empty(value: str | None, field_name: str) -> None:
    if value is None or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
