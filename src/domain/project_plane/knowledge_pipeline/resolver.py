from .snapshot import KnowledgePipelineSnapshot
from .states import KnowledgePipelineState


def _metrics_bool(snapshot: KnowledgePipelineSnapshot, key: str) -> bool:
    value = snapshot.metrics.get(key)
    return value is True


def resolve_pipeline_state(
    snapshot: KnowledgePipelineSnapshot,
) -> KnowledgePipelineState:
    if snapshot.document_status == "cancelled":
        return KnowledgePipelineState.CANCELLED

    stage = (snapshot.preprocessing_stage or "").strip()
    if snapshot.active_job_count > 0:
        if "compiler" in stage:
            return KnowledgePipelineState.COMPILER_RUNNING
        if "answer_resolution" in stage:
            return KnowledgePipelineState.ANSWER_RESOLUTION_RUNNING
        if "publication" in stage:
            return KnowledgePipelineState.PUBLICATION_RUNNING
        if "embedding" in stage:
            return KnowledgePipelineState.EMBEDDING_RUNNING
        if "retrieval_surface" in stage:
            return KnowledgePipelineState.RETRIEVAL_SURFACE_RUNNING

    if snapshot.compiler_batch_failed_count > 0:
        if snapshot.raw_candidate_count > 0:
            return KnowledgePipelineState.COMPILER_PARTIAL_FAILED
        return KnowledgePipelineState.COMPILER_FAILED

    all_batches_completed = (
        snapshot.compiler_batch_total_count > 0
        and snapshot.compiler_batch_completed_count
        >= snapshot.compiler_batch_total_count
    )
    if (
        all_batches_completed
        and snapshot.raw_candidate_count > 0
        and snapshot.canonical_entry_count == 0
    ):
        return KnowledgePipelineState.ANSWER_RESOLUTION_PENDING

    if snapshot.canonical_entry_count > 0 and _metrics_bool(
        snapshot, "fallback_publish_used"
    ):
        return KnowledgePipelineState.PARTIAL_PUBLISHED

    if snapshot.canonical_entry_count > 0 and snapshot.retrieval_surface_count == 0:
        if snapshot.active_error_code and snapshot.active_error_retryable:
            return KnowledgePipelineState.EMBEDDING_FAILED_RETRYABLE
        return KnowledgePipelineState.PUBLICATION_COMPLETED

    if snapshot.canonical_entry_count > 0:
        retrieval_matches_runtime = (
            snapshot.retrieval_surface_count == snapshot.runtime_entry_count
            and snapshot.retrieval_surface_count > 0
        )
        if retrieval_matches_runtime and snapshot.missing_embedding_count == 0:
            return KnowledgePipelineState.PROCESSED
        return KnowledgePipelineState.PROCESSED_WITH_WARNINGS

    return KnowledgePipelineState.INCONSISTENT
