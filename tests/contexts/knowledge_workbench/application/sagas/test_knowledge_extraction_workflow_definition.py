from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT,
    LEGACY_PHASE_MIGRATION_MAP,
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
    KnowledgeExtractionOperationContract,
    KnowledgeExtractionReadModelName,
    KnowledgeExtractionRecoveryScope,
    command_types_used_by_operations,
    event_types_used_by_operations,
    operation_by_command_type,
    operation_by_key,
    operations_for_phase,
)


def _operation(operation_key: str) -> KnowledgeExtractionOperationContract:
    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        if operation.operation_key == operation_key:
            return operation
    raise AssertionError(f"operation not found: {operation_key}")


def test_contract_terminal_phase_is_completed() -> None:
    assert (
        DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.terminal_phase
        is KnowledgeExtractionCanonicalPhase.COMPLETED
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


def test_every_canonical_command_type_is_bound_to_operation() -> None:
    assert command_types_used_by_operations() == frozenset(
        KnowledgeExtractionCanonicalCommandType
    )


def test_every_canonical_event_type_is_used_by_operation() -> None:
    out_of_band_workflow_control_events = frozenset(
        {
            KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED,
            KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED,
        }
    )

    assert event_types_used_by_operations() == (
        frozenset(KnowledgeExtractionCanonicalEventType)
        - out_of_band_workflow_control_events
    )


def test_start_workflow_operation_exists() -> None:
    operation = _operation("start_knowledge_extraction_workflow")

    assert operation.phase is KnowledgeExtractionCanonicalPhase.WORKFLOW_STARTED
    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.START_KNOWLEDGE_EXTRACTION_WORKFLOW
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.KNOWLEDGE_EXTRACTION_WORKFLOW_STARTED
    )
    assert operation.next_command_types == (
        KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT,
    )
    assert operation.owner_contexts == (
        "knowledge_workbench",
        "workflow_runtime",
    )
    assert operation.unit_of_work_name == "KnowledgeExtractionWorkflowStartUnitOfWork"
    assert operation.idempotency_key_template == (
        "knowledge-extraction-start:{workflow_run_id}"
    )
    assert operation.affected_read_models == (
        KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
        KnowledgeExtractionReadModelName.TIMELINE,
    )
    assert operation.recovery_scopes == (KnowledgeExtractionRecoveryScope.WORKFLOW,)
    assert operation.frontend_visibility is True


def test_ingest_source_document_has_source_document_persisted_intermediate_event() -> (
    None
):
    operation = _operation("ingest_source_document")

    assert operation.intermediate_event_types == (
        KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED,
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED
    )


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


def test_execute_claim_builder_section_has_started_and_capacity_intermediate_events() -> (
    None
):
    operation = _operation("execute_claim_builder_section")

    assert operation.intermediate_event_types == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_STARTED,
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED,
    )


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


def test_generate_embeddings_has_batch_completed_intermediate_event() -> None:
    operation = _operation("generate_draft_claim_embeddings")

    assert operation.intermediate_event_types == (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED,
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED
    )


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


def test_operation_by_key_returns_contract() -> None:
    assert operation_by_key("execute_claim_builder_section") == _operation(
        "execute_claim_builder_section"
    )


def test_operation_by_command_type_returns_contract() -> None:
    assert operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    ) == _operation("schedule_claim_builder_section_work")


def test_operations_for_phase_returns_claim_builder_section_operations() -> None:
    operations = operations_for_phase(
        KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION
    )

    assert tuple(operation.operation_key for operation in operations) == (
        "prepare_claim_builder_dispatch_batch",
        "split_claim_builder_source_unit",
        "execute_claim_builder_section",
        "reconcile_claim_builder_progress",
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


def test_legacy_phase_migration_map_covers_all_current_phase_keys() -> None:
    mapped_phase_keys = {
        mapping.legacy_phase_key for mapping in LEGACY_PHASE_MIGRATION_MAP
    }

    assert mapped_phase_keys == {
        phase_key.value for phase_key in KnowledgeExtractionPhaseKey
    }


def test_legacy_prompt_a_phases_map_to_claim_builder_phases() -> None:
    mapping_by_key = {
        mapping.legacy_phase_key: mapping for mapping in LEGACY_PHASE_MIGRATION_MAP
    }

    assert (
        mapping_by_key[
            KnowledgeExtractionPhaseKey.CLAIM_BUILDER_WORK_SCHEDULED.value
        ].canonical_phase
        is KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_WORK_SCHEDULING
    )
    assert (
        mapping_by_key[
            KnowledgeExtractionPhaseKey.CLAIM_BUILDER_SECTION_EXTRACTION_COMPLETED.value
        ].canonical_phase
        is KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION
    )
    assert (
        mapping_by_key[
            KnowledgeExtractionPhaseKey.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED.value
        ].canonical_phase
        is KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION
    )


def test_only_superseded_late_phases_are_out_of_current_contract() -> None:
    superseded_phase_keys = {
        KnowledgeExtractionPhaseKey.PROMPT_B_WORK_SCHEDULED.value,
        KnowledgeExtractionPhaseKey.PROMPT_B_WORK_COMPLETED.value,
        KnowledgeExtractionPhaseKey.FINAL_KNOWLEDGE_PREPARED.value,
        KnowledgeExtractionPhaseKey.REVIEW_COMPLETED.value,
        KnowledgeExtractionPhaseKey.INTERMEDIATE_ARTIFACTS_CLEANED.value,
    }
    mapping_by_key = {
        mapping.legacy_phase_key: mapping for mapping in LEGACY_PHASE_MIGRATION_MAP
    }

    for legacy_phase_key in superseded_phase_keys:
        mapping = mapping_by_key[legacy_phase_key]
        assert (
            mapping.canonical_phase
            is KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY
        )
        assert mapping.migration_status == "out_of_current_contract"

    assert (
        mapping_by_key[KnowledgeExtractionPhaseKey.PUBLISHED.value].canonical_phase
        is KnowledgeExtractionCanonicalPhase.PUBLICATION
    )
    assert (
        mapping_by_key[
            KnowledgeExtractionPhaseKey.RETRIEVAL_EMBEDDINGS_BUILT.value
        ].canonical_phase
        is KnowledgeExtractionCanonicalPhase.PUBLICATION
    )
    assert (
        mapping_by_key[KnowledgeExtractionPhaseKey.DONE.value].canonical_phase
        is KnowledgeExtractionCanonicalPhase.COMPLETED
    )


def test_prepare_dispatch_batch_can_route_source_unit_split_required() -> None:
    operation = _operation("prepare_claim_builder_dispatch_batch")

    assert (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_REQUIRED
        in operation.intermediate_event_types
    )
    assert (
        KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT
        in operation.next_command_types
    )


def test_split_claim_builder_source_unit_operation_contract() -> None:
    operation = _operation("split_claim_builder_source_unit")

    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_COMPLETED
    )
    assert operation.next_command_types == (
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK,
    )
    assert set(operation.recovery_scopes) >= {
        KnowledgeExtractionRecoveryScope.SOURCE_UNIT,
        KnowledgeExtractionRecoveryScope.CLAIM_BUILDER_SECTION,
    }


def test_apply_draft_claim_compaction_result_operation_contract() -> None:
    operation = _operation("apply_draft_claim_compaction_result")

    assert operation.phase is KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING
    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED
    )
    assert set(operation.intermediate_event_types) == {
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_CLUSTER_DONE,
    }
    assert set(operation.affected_read_models) == {
        KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
        KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
        KnowledgeExtractionReadModelName.TIMELINE,
    }
    assert set(operation.recovery_scopes) == {
        KnowledgeExtractionRecoveryScope.CLUSTER_BUILD,
        KnowledgeExtractionRecoveryScope.WORK_ITEM_ATTEMPT,
    }
    assert operation.frontend_visibility is True


def test_cluster_draft_claims_routes_to_compaction_dispatch_preparation() -> None:
    operation = _operation("cluster_draft_claims")

    assert operation.next_command_types == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
    )


def test_reconcile_draft_claim_compaction_progress_operation_contract() -> None:
    operation = _operation("reconcile_draft_claim_compaction_progress")

    assert operation.phase is KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING
    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED
    )
    assert operation.intermediate_event_types == (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE,
    )
    assert operation.next_command_types == (
        KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE,
    )
    assert operation.owner_contexts == (
        "knowledge_workbench",
        "execution_runtime",
        "workflow_runtime",
    )
    assert set(operation.affected_read_models) == {
        KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
        KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
        KnowledgeExtractionReadModelName.TIMELINE,
    }


def test_prepare_draft_claim_compaction_dispatch_batch_operation_contract() -> None:
    operation = _operation("prepare_draft_claim_compaction_dispatch_batch")

    assert operation.phase is KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING
    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED
    )
    assert operation.next_command_types == (
        KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION,
    )
    assert operation.owner_contexts == (
        "knowledge_workbench",
        "execution_runtime",
        "llm_runtime",
        "capacity_runtime",
    )
    assert set(operation.affected_read_models) == {
        KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
        KnowledgeExtractionReadModelName.CAPACITY_STATUS,
        KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
        KnowledgeExtractionReadModelName.TIMELINE,
    }


def test_execute_draft_claim_compaction_operation_contract() -> None:
    operation = _operation("execute_draft_claim_compaction")

    assert operation.phase is KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING
    assert (
        operation.command_type
        is KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION
    )
    assert (
        operation.success_event_type
        is KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED
    )
    assert set(operation.next_command_types) == {
        KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS,
    }
    assert operation.owner_contexts == (
        "knowledge_workbench",
        "execution_runtime",
        "llm_runtime",
        "capacity_runtime",
        "workflow_runtime",
    )
