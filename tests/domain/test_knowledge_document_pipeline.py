import pytest

from src.domain.project_plane.knowledge_document_pipeline import (
    ALLOWED_TRANSITIONS,
    KnowledgeDocumentPipelineCommand,
    KnowledgeDocumentPipelineError,
    KnowledgeDocumentPipelineState,
    KnowledgeDocumentPipelineErrorCode,
    KnowledgeDocumentPipelineErrorSeverity,
    allowed_actions_for_state,
    recommended_action_for_state,
    resolve_pipeline_state,
    state_hash,
    validate_transition,
)


def test_all_pipeline_commands_have_explicit_transition() -> None:
    covered = {command for _, command in ALLOWED_TRANSITIONS}
    for command in KnowledgeDocumentPipelineCommand:
        assert command in covered


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


def test_recommended_action_for_partial_failed() -> None:
    action = recommended_action_for_state(
        KnowledgeDocumentPipelineState.COMPILER_PARTIAL_FAILED
    )
    assert action is not None
    assert action[0] == "retry_failed_batches"


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


def test_state_hash_is_deterministic() -> None:
    one = state_hash(KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING, 17)
    two = state_hash(KnowledgeDocumentPipelineState.ANSWER_RESOLUTION_PENDING, 17)
    assert one == two


def test_pipeline_error_taxonomy_contains_provider_capacity() -> None:
    assert (
        KnowledgeDocumentPipelineErrorCode.LLM_PROVIDER_OVER_CAPACITY.value
        == "llm_provider_over_capacity"
    )
    assert (
        KnowledgeDocumentPipelineErrorSeverity.RECOVERABLE_ERROR.value
        == "recoverable_error"
    )
