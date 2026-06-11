from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT,
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
    KnowledgeExtractionReadModelName,
    KnowledgeExtractionRecoveryScope,
)


def _operation(operation_key: str):
    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        if operation.operation_key == operation_key:
            return operation
    raise AssertionError(f"operation not found: {operation_key}")


def test_contract_terminal_phase_is_cluster_preview_ready() -> None:
    assert (
        DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.terminal_phase
        is KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY
    )


def test_operation_keys_are_unique() -> None:
    operation_keys = tuple(
        operation.operation_key
        for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations
    )

    assert len(operation_keys) == len(set(operation_keys))


def test_operation_metadata_is_non_empty() -> None:
    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        assert operation.unit_of_work_name
        assert operation.owner_contexts
        assert all(owner_context for owner_context in operation.owner_contexts)
        assert operation.idempotency_key_template


def test_primary_command_types_are_unique() -> None:
    command_types = tuple(
        operation.command_type
        for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations
    )

    assert len(command_types) == len(set(command_types))


def test_claim_builder_section_execution_operation_contract() -> None:
    operation = _operation("execute_claim_builder_section")

    assert operation.phase is (
        KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION
    )
    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED
    )


def test_claim_builder_section_execution_failure_events() -> None:
    operation = _operation("execute_claim_builder_section")

    assert set(operation.failure_event_types) == {
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_SPLIT_REQUIRED,
    }


def test_claim_builder_section_execution_read_models() -> None:
    operation = _operation("execute_claim_builder_section")

    assert set(operation.affected_read_models) >= {
        KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
        KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
        KnowledgeExtractionReadModelName.RECENT_CLAIMS,
        KnowledgeExtractionReadModelName.TIMELINE,
        KnowledgeExtractionReadModelName.CAPACITY_STATUS,
    }


def test_claim_builder_section_execution_recovery_scopes() -> None:
    operation = _operation("execute_claim_builder_section")

    assert set(operation.recovery_scopes) >= {
        KnowledgeExtractionRecoveryScope.SOURCE_UNIT,
        KnowledgeExtractionRecoveryScope.WORK_ITEM_ATTEMPT,
        KnowledgeExtractionRecoveryScope.CLAIM_BUILDER_SECTION,
    }


def test_contract_has_embedding_and_clustering_operations() -> None:
    assert (
        _operation("generate_draft_claim_embeddings").command_type
        is KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS
    )
    assert (
        _operation("cluster_draft_claims").command_type
        is KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
    )


def test_contract_stops_at_cluster_preview_and_review_pause() -> None:
    build_preview = _operation("build_cluster_preview")
    pause_review = _operation("pause_for_cluster_contract_review")

    assert (
        build_preview.success_event_type
        is KnowledgeExtractionCanonicalEventType.CLUSTER_PREVIEW_READY
    )
    assert (
        pause_review.success_event_type
        is KnowledgeExtractionCanonicalEventType.CLUSTER_CONTRACT_REVIEW_REQUIRED
    )
    assert pause_review.next_command_types == ()
    assert (
        DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations[-1].operation_key
        == "pause_for_cluster_contract_review"
    )


def test_operation_keys_use_claim_builder_vocabulary() -> None:
    forbidden_fragments = (
        "prompt_a",
        "draft_observation",
    )

    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        assert all(
            fragment not in operation.operation_key for fragment in forbidden_fragments
        )


def test_no_separate_llm_output_or_materialization_operations() -> None:
    forbidden_fragments = (
        "llm_output",
        "materialize_claims",
    )

    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        assert all(
            fragment not in operation.operation_key for fragment in forbidden_fragments
        )


def test_no_persist_or_materialize_prompt_a_commands_exist() -> None:
    forbidden_names = {
        "PERSIST_PROMPT_A_SECTION_LLM_OUTPUT",
        "MATERIALIZE_PROMPT_A_SECTION_CLAIMS",
        "PERSIST_CLAIM_BUILDER_LLM_OUTPUT",
        "MATERIALIZE_CLAIM_BUILDER_CLAIMS",
    }

    assert forbidden_names.isdisjoint(
        KnowledgeExtractionCanonicalCommandType.__members__
    )
