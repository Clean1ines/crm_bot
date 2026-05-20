from enum import StrEnum


class KnowledgePipelineState(StrEnum):
    UPLOADED = "uploaded"
    SOURCE_UNITS_READY = "source_units_ready"

    COMPILER_RUNNING = "compiler_running"
    COMPILER_PARTIAL_FAILED = "compiler_partial_failed"
    COMPILER_FAILED = "compiler_failed"
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
    RUNNING_STALE = "running_stale"
    INCONSISTENT = "inconsistent"
