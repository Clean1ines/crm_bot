from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class KnowledgePipelineSnapshot:
    document_id: str
    document_status: str
    preprocessing_status: str | None
    preprocessing_stage: str | None

    source_unit_count: int
    compiler_batch_total_count: int
    compiler_batch_completed_count: int
    compiler_batch_failed_count: int
    compiler_batch_processing_count: int
    compiler_batch_pending_count: int

    raw_candidate_count: int
    canonical_entry_count: int
    runtime_entry_count: int
    retrieval_surface_count: int
    missing_embedding_count: int

    active_job_count: int
    active_job_type: str | None
    active_job_status: str | None

    active_error_code: str | None
    active_error_retryable: bool
    last_error_code: str | None

    metrics: Mapping[str, object]
