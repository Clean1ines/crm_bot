from src.domain.project_plane.knowledge_pipeline import (
    KnowledgePipelineCommand,
    KnowledgePipelineSnapshot,
    KnowledgePipelineState,
    allowed_actions_for_state,
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


def test_compiler_partial_failed_allows_retry_and_fallback_publish() -> None:
    actions = allowed_actions_for_state(
        KnowledgePipelineState.COMPILER_PARTIAL_FAILED,
        _snapshot(compiler_batch_failed_count=1, raw_candidate_count=1),
    )
    assert KnowledgePipelineCommand.RETRY_FAILED_COMPILER_BATCHES in actions
    assert KnowledgePipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION in actions


def test_answer_resolution_pending_allows_resume_and_fallback_publish() -> None:
    actions = allowed_actions_for_state(
        KnowledgePipelineState.ANSWER_RESOLUTION_PENDING,
        _snapshot(raw_candidate_count=5, compiler_batch_completed_count=2),
    )
    assert KnowledgePipelineCommand.RESUME_KNOWLEDGE_COMPILATION in actions
    assert KnowledgePipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION in actions


def test_processed_allows_open_curation_console() -> None:
    actions = allowed_actions_for_state(KnowledgePipelineState.PROCESSED, _snapshot())
    assert KnowledgePipelineCommand.OPEN_CURATION_CONSOLE in actions


def test_retry_is_not_allowed_after_processed() -> None:
    actions = allowed_actions_for_state(KnowledgePipelineState.PROCESSED, _snapshot())
    assert KnowledgePipelineCommand.RETRY_FAILED_COMPILER_BATCHES not in actions
