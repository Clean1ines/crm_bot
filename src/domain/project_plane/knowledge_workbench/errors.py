from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .shared import (
    DocumentId,
    DomainInvariantError,
    ErrorReportId,
    NodeRunId,
    ProcessingRunId,
    ProjectId,
    SectionId,
    require_document_id,
    require_processing_run_id,
    require_project_id,
)


class ProcessingErrorKind(StrEnum):
    VALIDATION = "validation"
    INPUT_TOO_LARGE = "input_too_large"
    GROQ_RATE_LIMIT = "groq_rate_limit"
    GROQ_DAILY_LIMIT = "groq_daily_limit"
    PROVIDER_ERROR = "provider_error"
    NETWORK_ERROR = "network_error"
    RENDER_SHUTDOWN = "render_shutdown"
    CANCELLED_BY_USER = "cancelled_by_user"
    DELETED_DOCUMENT = "deleted_document"
    STALE_JOB = "stale_job"
    UNKNOWN = "unknown"


class ProcessingRecoverability(StrEnum):
    AUTO_RESUMABLE = "auto_resumable"
    MANUAL_RESUMABLE = "manual_resumable"
    FATAL = "fatal"
    IGNORED_STALE = "ignored_stale"


@dataclass(frozen=True, slots=True)
class ProcessingErrorReport:
    error_id: ErrorReportId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    error_kind: ProcessingErrorKind
    user_message: str
    internal_message: str
    recoverability: ProcessingRecoverability
    created_at: datetime | None = None
    node_run_id: NodeRunId | None = None
    section_id: SectionId | None = None

    def __post_init__(self) -> None:
        if not self.error_id:
            raise DomainInvariantError("error_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.user_message:
            raise DomainInvariantError("user_message is required")
        if not self.internal_message:
            raise DomainInvariantError("internal_message is required")
