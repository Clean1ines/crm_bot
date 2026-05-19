import pytest

from src.domain.project_plane.knowledge_document_pipeline import (
    KnowledgeDocumentPipelineCommand,
    KnowledgeDocumentPipelineError,
    KnowledgeDocumentPipelineState,
    ALLOWED_TRANSITIONS,
    allowed_actions_for_state,
    resolve_pipeline_state,
    validate_transition,
)


def test_all_pipeline_commands_have_explicit_transition() -> None:
    covered = {command for _, command in ALLOWED_TRANSITIONS}
    assert KnowledgeDocumentPipelineCommand.RETRY_FAILED_COMPILER_BATCHES in covered
    assert KnowledgeDocumentPipelineCommand.RESUME_KNOWLEDGE_COMPILATION in covered
    assert (
        KnowledgeDocumentPipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION in covered
    )


def test_validate_transition_rejects_illegal_transition() -> None:
    with pytest.raises(KnowledgeDocumentPipelineError):
        validate_transition(
            KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING,
            KnowledgeDocumentPipelineCommand.COMPLETE_EMBEDDINGS,
        )


def test_allowed_actions_for_answer_resolution_pending() -> None:
    actions = allowed_actions_for_state(
        KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING
    )
    assert [action.id for action in actions] == [
        "resume_processing",
        "publish_raw_drafts_without_resolution",
    ]


def test_resolve_pipeline_state_prefers_processed_when_surface_ready() -> None:
    state = resolve_pipeline_state(
        document_status="processed",
        preprocessing_status="completed",
        pipeline_stage="completed",
        batch_total=10,
        batch_failed=0,
        has_raw_drafts=True,
        has_canonical_entries=True,
        has_retrieval_surface=True,
    )
    assert state == KnowledgeDocumentPipelineState.PROCESSED
