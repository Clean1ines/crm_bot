from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .shared import (
    DocumentId,
    DomainInvariantError,
    JsonValue,
    ProcessingRunId,
    ProjectId,
    SectionId,
    SourceType,
    require_document_id,
    require_project_id,
)


class KnowledgeDocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    SECTIONED = "sectioned"
    PROCESSING = "processing"
    PARTIALLY_PROCESSED = "partially_processed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    PROCESSED = "processed"
    PUBLISHED = "published"
    FAILED = "failed"
    DELETED = "deleted"


class KnowledgeDocumentUploadActorType(StrEnum):
    UNKNOWN = "unknown"
    WEB_USER = "web_user"
    TELEGRAM_USER = "telegram_user"
    PLATFORM_ADMIN = "platform_admin"
    SYSTEM = "system"
    IMPORT = "import"


class DocumentSectionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    FAILED = "failed"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    document_id: DocumentId
    project_id: ProjectId
    file_name: str
    source_type: SourceType
    content_hash: str
    upload_id: str
    file_size_bytes: int
    status: KnowledgeDocumentStatus
    current_processing_run_id: ProcessingRunId | None = None
    uploaded_by_user_id: str | None = None
    uploaded_by_actor_type: KnowledgeDocumentUploadActorType = (
        KnowledgeDocumentUploadActorType.UNKNOWN
    )
    uploaded_by_actor_id: str | None = None
    trusted_upload: bool = False
    last_error_kind: str | None = None
    last_error_message: str | None = None
    last_error_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.file_name:
            raise DomainInvariantError("file_name is required")
        if not self.content_hash:
            raise DomainInvariantError("content_hash is required")
        if self.file_size_bytes < 0:
            raise DomainInvariantError("file_size_bytes must be non-negative")
        if (
            self.uploaded_by_user_id is not None
            and not self.uploaded_by_user_id.strip()
        ):
            raise DomainInvariantError("uploaded_by_user_id must be non-empty")
        if (
            self.uploaded_by_actor_id is not None
            and not self.uploaded_by_actor_id.strip()
        ):
            raise DomainInvariantError("uploaded_by_actor_id must be non-empty")
        if self.last_error_at is not None and not (
            self.last_error_kind or self.last_error_message
        ):
            raise DomainInvariantError(
                "last_error_at requires last_error_kind or last_error_message"
            )
        if self.status is KnowledgeDocumentStatus.DELETED and self.deleted_at is None:
            raise DomainInvariantError("deleted document must have deleted_at")

    @property
    def is_deleted(self) -> bool:
        return self.status is KnowledgeDocumentStatus.DELETED


@dataclass(frozen=True, slots=True)
class DocumentSection:
    section_id: SectionId
    document_id: DocumentId
    project_id: ProjectId
    section_index: int
    section_key: str
    heading_path: tuple[str, ...]
    title: str
    raw_text: str
    normalized_text: str
    source_refs: tuple[str, ...]
    source_chunk_indexes: tuple[int, ...]
    status: DocumentSectionStatus
    parent_section_id: SectionId | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.section_id:
            raise DomainInvariantError("section_id is required")
        if self.section_index < 0:
            raise DomainInvariantError("section_index must be non-negative")
        if not self.section_key:
            raise DomainInvariantError("section_key is required")
        if self.status is not DocumentSectionStatus.DELETED and not self.raw_text:
            raise DomainInvariantError("non-deleted section must have raw_text")


def ensure_document_can_be_processed(document: KnowledgeDocument) -> None:
    if document.is_deleted:
        raise DomainInvariantError("deleted document cannot be processed")


def ensure_document_can_be_resumed(document: KnowledgeDocument) -> None:
    if document.is_deleted:
        raise DomainInvariantError("deleted document cannot be resumed")


def ensure_document_can_be_published(document: KnowledgeDocument) -> None:
    if document.is_deleted:
        raise DomainInvariantError("deleted document cannot be published")


def ensure_document_can_be_evaluated(document: KnowledgeDocument) -> None:
    if document.is_deleted:
        raise DomainInvariantError("deleted document cannot participate in RAG eval")
