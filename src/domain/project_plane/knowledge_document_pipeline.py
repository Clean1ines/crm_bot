from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


class KnowledgeDocumentPipelineState(StrEnum):
    UPLOADED = "uploaded"
    SOURCE_EXTRACTION_RUNNING = "source_extraction_running"
    SOURCE_UNITS_READY = "source_units_ready"
    COMPILER_RUNNING = "compiler_running"
    COMPILER_PARTIAL_FAILED = "compiler_partial_failed"
    COMPILER_COMPLETED = "compiler_completed"
    ANSWER_RESOLUTION_PENDING = "answer_resolution_pending"
    ANSWER_RESOLUTION_RUNNING = "answer_resolution_running"
    ANSWER_RESOLUTION_FAILED = "answer_resolution_failed"
    ANSWER_RESOLUTION_COMPLETED = "answer_resolution_completed"
    PUBLICATION_PENDING = "publication_pending"
    PUBLICATION_RUNNING = "publication_running"
    PUBLICATION_COMPLETED = "publication_completed"
    EMBEDDING_RUNNING = "embedding_running"
    EMBEDDING_FAILED_RETRYABLE = "embedding_failed_retryable"
    EMBEDDING_FAILED_FATAL = "embedding_failed_fatal"
    RETRIEVAL_SURFACE_RUNNING = "retrieval_surface_running"
    RETRIEVAL_SURFACE_COMPLETED = "retrieval_surface_completed"
    PROCESSED = "processed"
    PROCESSED_WITH_WARNINGS = "processed_with_warnings"
    PARTIAL_PUBLISHED = "partial_published"
    CANCELLED = "cancelled"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FATAL = "failed_fatal"


class KnowledgeDocumentPipelineCommand(StrEnum):
    RETRY_FAILED_COMPILER_BATCHES = "retry_failed_compiler_batches"
    RESUME_KNOWLEDGE_COMPILATION = "resume_knowledge_compilation"
    PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION = "publish_raw_drafts_without_resolution"
    CANCEL_KNOWLEDGE_PROCESSING = "cancel_knowledge_processing"
    RETIGHTEN_PUBLISHED_ENTRIES = "retighten_published_entries"
    COMPLETE_ANSWER_RESOLUTION = "complete_answer_resolution"
    COMPLETE_PUBLICATION = "complete_publication"
    COMPLETE_EMBEDDINGS = "complete_embeddings"
    COMPLETE_RETRIEVAL_SURFACE = "complete_retrieval_surface"


class KnowledgeDocumentPipelineActionKind(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SECONDARY_WARNING = "secondary_warning"
    DESTRUCTIVE = "destructive"


class KnowledgeDocumentPipelineErrorCode(StrEnum):
    LLM_PROVIDER_OVER_CAPACITY = "llm_provider_over_capacity"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_TIMEOUT = "llm_timeout"
    LLM_CONNECTION_ERROR = "llm_connection_error"
    LLM_INVALID_JSON = "llm_invalid_json"
    LLM_SCHEMA_VALIDATION_ERROR = "llm_schema_validation_error"
    EMBEDDING_PROVIDER_UNAVAILABLE = "embedding_provider_unavailable"
    EMBEDDING_VECTOR_COUNT_MISMATCH = "embedding_vector_count_mismatch"
    UNKNOWN_LLM_ERROR = "unknown_llm_error"
    UNKNOWN_EMBEDDING_ERROR = "unknown_embedding_error"


class KnowledgeDocumentPipelineErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    RECOVERABLE_ERROR = "recoverable_error"
    FATAL_ERROR = "fatal_error"
    TECHNICAL_DIAGNOSTIC = "technical_diagnostic"


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentPipelineAction:
    id: str
    label: str
    kind: KnowledgeDocumentPipelineActionKind
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentPipelineErrorInfo:
    code: KnowledgeDocumentPipelineErrorCode
    severity: KnowledgeDocumentPipelineErrorSeverity
    retryable: bool
    user_message: str
    technical_message: str = ""
    provider: str | None = None
    model: str | None = None
    status_code: int | None = None
    job_id: str | None = None
    batch_index: int | None = None
    timestamp: str | None = None


class KnowledgeDocumentPipelineError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[
    tuple[KnowledgeDocumentPipelineState, KnowledgeDocumentPipelineCommand],
    KnowledgeDocumentPipelineState,
] = {
    (KnowledgeDocumentPipelineState.COMPILER_PARTIAL_FAILED, KnowledgeDocumentPipelineCommand.RETRY_FAILED_COMPILER_BATCHES): KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING,
    (KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING, KnowledgeDocumentPipelineCommand.RESUME_KNOWLEDGE_COMPILATION): KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING,
    (KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING, KnowledgeDocumentPipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION): KnowledgeDocumentPipelineState.PARTIAL_PUBLISHED,
    (KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING, KnowledgeDocumentPipelineCommand.COMPLETE_ANSWER_RESOLUTION): KnowledgeDocumentPipelineState.PUBLICATION_RUNNING,
    (KnowledgeDocumentPipelineState.PUBLICATION_RUNNING, KnowledgeDocumentPipelineCommand.COMPLETE_PUBLICATION): KnowledgeDocumentPipelineState.EMBEDDING_RUNNING,
    (KnowledgeDocumentPipelineState.EMBEDDING_RUNNING, KnowledgeDocumentPipelineCommand.COMPLETE_EMBEDDINGS): KnowledgeDocumentPipelineState.RETRIEVAL_SURFACE_RUNNING,
    (KnowledgeDocumentPipelineState.RETRIEVAL_SURFACE_RUNNING, KnowledgeDocumentPipelineCommand.COMPLETE_RETRIEVAL_SURFACE): KnowledgeDocumentPipelineState.PROCESSED,
    (KnowledgeDocumentPipelineState.COMPILER_RUNNING, KnowledgeDocumentPipelineCommand.CANCEL_KNOWLEDGE_PROCESSING): KnowledgeDocumentPipelineState.CANCELLED,
    (KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING, KnowledgeDocumentPipelineCommand.CANCEL_KNOWLEDGE_PROCESSING): KnowledgeDocumentPipelineState.CANCELLED,
    (KnowledgeDocumentPipelineState.PUBLICATION_RUNNING, KnowledgeDocumentPipelineCommand.CANCEL_KNOWLEDGE_PROCESSING): KnowledgeDocumentPipelineState.CANCELLED,
    (KnowledgeDocumentPipelineState.EMBEDDING_RUNNING, KnowledgeDocumentPipelineCommand.CANCEL_KNOWLEDGE_PROCESSING): KnowledgeDocumentPipelineState.CANCELLED,
    (KnowledgeDocumentPipelineState.RETRIEVAL_SURFACE_RUNNING, KnowledgeDocumentPipelineCommand.CANCEL_KNOWLEDGE_PROCESSING): KnowledgeDocumentPipelineState.CANCELLED,
    (KnowledgeDocumentPipelineState.PROCESSED, KnowledgeDocumentPipelineCommand.RETIGHTEN_PUBLISHED_ENTRIES): KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING,
    (KnowledgeDocumentPipelineState.PUBLICATION_COMPLETED, KnowledgeDocumentPipelineCommand.RETIGHTEN_PUBLISHED_ENTRIES): KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING,
}


def validate_transition(state: KnowledgeDocumentPipelineState, command: KnowledgeDocumentPipelineCommand) -> KnowledgeDocumentPipelineState:
    next_state = ALLOWED_TRANSITIONS.get((state, command))
    if next_state is None:
        raise KnowledgeDocumentPipelineError(f"invalid knowledge pipeline transition: {state} -> {command}")
    return next_state


def resolve_pipeline_state(*, document_status: str, preprocessing_status: str, pipeline_stage: str, batch_total: int, batch_failed: int, has_raw_drafts: bool, has_canonical_entries: bool, has_retrieval_surface: bool) -> KnowledgeDocumentPipelineState:
    if has_retrieval_surface and document_status == "processed":
        return KnowledgeDocumentPipelineState.PROCESSED
    if pipeline_stage == "answer_resolution" and preprocessing_status == "processing":
        return KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING
    if batch_failed > 0:
        return KnowledgeDocumentPipelineState.COMPILER_PARTIAL_FAILED
    if has_canonical_entries and not has_retrieval_surface:
        return KnowledgeDocumentPipelineState.PUBLICATION_COMPLETED
    if has_raw_drafts and batch_total > 0:
        return KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING
    if preprocessing_status == "processing":
        return KnowledgeDocumentPipelineState.COMPILER_RUNNING
    if preprocessing_status == "cancelled":
        return KnowledgeDocumentPipelineState.CANCELLED
    if preprocessing_status == "failed" or document_status == "error":
        return KnowledgeDocumentPipelineState.FAILED_RETRYABLE
    return KnowledgeDocumentPipelineState.UPLOADED


def recommended_action_for_state(state: KnowledgeDocumentPipelineState) -> tuple[str, str] | None:
    if state == KnowledgeDocumentPipelineState.COMPILER_PARTIAL_FAILED:
        return ("retry_failed_batches", "Есть проблемные части документа — повторите их обработку")
    if state == KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING:
        return ("resume_processing", "Все черновики готовы, можно продолжить уплотнение")
    return None


def state_hash(state: KnowledgeDocumentPipelineState, version: int) -> str:
    return sha256(f"{state.value}:{version}".encode("utf-8")).hexdigest()[:16]


def allowed_actions_for_state(state: KnowledgeDocumentPipelineState) -> tuple[KnowledgeDocumentPipelineAction, ...]:
    if state == KnowledgeDocumentPipelineState.COMPILER_PARTIAL_FAILED:
        return (KnowledgeDocumentPipelineAction(id="retry_failed_batches", label="Повторить проблемные части", kind=KnowledgeDocumentPipelineActionKind.PRIMARY),)
    if state == KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING:
        return (
            KnowledgeDocumentPipelineAction(id="resume_processing", label="Продолжить обработку", kind=KnowledgeDocumentPipelineActionKind.PRIMARY),
            KnowledgeDocumentPipelineAction(id="publish_raw_drafts_without_resolution", label="Опубликовать черновики без уплотнения", kind=KnowledgeDocumentPipelineActionKind.SECONDARY_WARNING),
        )
    if state in {KnowledgeDocumentPipelineState.COMPILER_RUNNING, KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_RUNNING, KnowledgeDocumentPipelineState.PUBLICATION_RUNNING, KnowledgeDocumentPipelineState.EMBEDDING_RUNNING, KnowledgeDocumentPipelineState.RETRIEVAL_SURFACE_RUNNING}:
        return (KnowledgeDocumentPipelineAction(id="cancel", label="Остановить обработку", kind=KnowledgeDocumentPipelineActionKind.DESTRUCTIVE),)
    if state in {KnowledgeDocumentPipelineState.PUBLICATION_COMPLETED, KnowledgeDocumentPipelineState.PARTIAL_PUBLISHED, KnowledgeDocumentPipelineState.PROCESSED, KnowledgeDocumentPipelineState.PROCESSED_WITH_WARNINGS}:
        return (KnowledgeDocumentPipelineAction(id="review_published", label="Проверить опубликованные ответы", kind=KnowledgeDocumentPipelineActionKind.SECONDARY),)
    return ()
