import pytest

from src.domain.project_plane.knowledge_pipeline import (
    KnowledgePipelineCommand,
    KnowledgePipelineSnapshot,
    KnowledgePipelineState,
    validate_pipeline_command,
)
from src.domain.project_plane.knowledge_pipeline.errors import (
    KnowledgePipelineValidationError,
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
        compiler_batch_failed_count=1,
        compiler_batch_processing_count=0,
        compiler_batch_pending_count=1,
        raw_candidate_count=1,
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


def test_validate_pipeline_command_rejects_disallowed_command() -> None:
    with pytest.raises(KnowledgePipelineValidationError):
        validate_pipeline_command(
            KnowledgePipelineState.COMPILER_PARTIAL_FAILED,
            KnowledgePipelineCommand.OPEN_CURATION_CONSOLE,
            _snapshot(),
        )
