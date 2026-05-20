from src.domain.project_plane.knowledge_pipeline import (
    KnowledgePipelineSnapshot,
    KnowledgePipelineState,
    resolve_pipeline_state,
)


def _snapshot(**overrides: object) -> KnowledgePipelineSnapshot:
    base = dict(
        document_id="doc-1",
        document_status="processing",
        preprocessing_status="processing",
        preprocessing_stage=None,
        source_unit_count=10,
        compiler_batch_total_count=2,
        compiler_batch_completed_count=0,
        compiler_batch_failed_count=0,
        compiler_batch_processing_count=0,
        compiler_batch_pending_count=2,
        raw_candidate_count=0,
        canonical_entry_count=0,
        runtime_entry_count=0,
        retrieval_surface_count=0,
        missing_embedding_count=0,
        active_job_count=0,
        active_job_type=None,
        active_job_status=None,
        active_error_code=None,
        active_error_retryable=False,
        last_error_code=None,
        metrics={},
    )
    base.update(overrides)
    return KnowledgePipelineSnapshot(**base)


def test_failed_batch_with_drafts_resolves_compiler_partial_failed() -> None:
    snapshot = _snapshot(compiler_batch_failed_count=1, raw_candidate_count=3)
    assert (
        resolve_pipeline_state(snapshot)
        == KnowledgePipelineState.COMPILER_PARTIAL_FAILED
    )


def test_all_batches_completed_with_raw_candidates_and_no_canonical_entries_resolves_answer_resolution_pending() -> (
    None
):
    snapshot = _snapshot(
        compiler_batch_total_count=3,
        compiler_batch_completed_count=3,
        raw_candidate_count=7,
        canonical_entry_count=0,
    )
    assert (
        resolve_pipeline_state(snapshot)
        == KnowledgePipelineState.ANSWER_RESOLUTION_PENDING
    )


def test_canonical_entries_without_retrieval_surface_is_not_processed() -> None:
    snapshot = _snapshot(canonical_entry_count=3, retrieval_surface_count=0)
    assert resolve_pipeline_state(snapshot) != KnowledgePipelineState.PROCESSED


def test_processed_requires_runtime_entries_retrieval_surface_and_embeddings() -> None:
    processed = _snapshot(
        canonical_entry_count=2,
        runtime_entry_count=2,
        retrieval_surface_count=2,
        missing_embedding_count=0,
    )
    assert resolve_pipeline_state(processed) == KnowledgePipelineState.PROCESSED

    not_processed = _snapshot(
        canonical_entry_count=2,
        runtime_entry_count=2,
        retrieval_surface_count=2,
        missing_embedding_count=1,
    )
    assert resolve_pipeline_state(not_processed) != KnowledgePipelineState.PROCESSED
