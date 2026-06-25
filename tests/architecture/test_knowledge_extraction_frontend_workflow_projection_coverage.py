from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECTORS_DIR = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "observability"
    / "application"
    / "projectors"
)
EMBEDDING_HANDLER_PATH = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "application"
    / "sagas"
    / "handle_generate_draft_claim_embeddings_command.py"
)
CLUSTER_HANDLER_PATH = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "application"
    / "sagas"
    / "handle_cluster_draft_claims_command.py"
)
SOURCE_INGESTION_PROJECTOR_PATH = (
    PROJECTORS_DIR / "source_ingestion_frontend_workflow_event_projector.py"
)
CLAIM_BUILDER_SCHEDULING_PROJECTOR_PATH = (
    PROJECTORS_DIR
    / "claim_builder_work_scheduling_frontend_workflow_event_projector.py"
)
CLAIM_BUILDER_DISPATCH_PROJECTOR_PATH = (
    PROJECTORS_DIR / "claim_builder_dispatch_batch_frontend_workflow_event_projector.py"
)
CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH = (
    PROJECTORS_DIR
    / "claim_builder_section_outcome_frontend_workflow_event_projector.py"
)
CAPACITY_WINDOW_PROJECTOR_PATH = (
    PROJECTORS_DIR / "capacity_window_frontend_workflow_event_projector.py"
)
PROJECT_FRONTEND_WORKFLOW_EVENT_PATH = (
    PROJECTORS_DIR / "project_frontend_workflow_event.py"
)
WORKFLOW_DEFINITION_PATH = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "application"
    / "sagas"
    / "knowledge_extraction_workflow_definition.py"
)
RESUME_COMPOSITION_PATH = (
    ROOT
    / "src"
    / "interfaces"
    / "composition"
    / "knowledge_extraction_workflow_resume.py"
)
AFTER_UPLOAD_COMPOSITION_PATH = (
    ROOT
    / "src"
    / "interfaces"
    / "composition"
    / "knowledge_extraction_workflow_after_upload.py"
)
KNOWLEDGE_HTTP_PATH = ROOT / "src" / "interfaces" / "http" / "knowledge.py"

_FUTURE_UNCOVERED_EVENT_MARKERS = (
    "DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED",
    "DRAFT_CLAIM_COMPACTION_ATTEMPT_STARTED",
    "DRAFT_CLAIM_COMPACTION_RESULT_APPLIED",
    "DRAFT_CLAIM_CURATION_WORKSPACE_OPENED",
    "DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED",
)


def test_embedding_canonical_events_have_projector_modules() -> None:
    assert (
        PROJECTORS_DIR / "draft_claim_embedding_frontend_workflow_event_projector.py"
    ).is_file()
    assert (
        PROJECTORS_DIR / "draft_claim_cluster_frontend_workflow_event_projector.py"
    ).is_file()
    assert (
        PROJECTORS_DIR / "knowledge_extraction_frontend_workflow_event_projector.py"
    ).is_file()


def test_embedding_handler_supports_frontend_projection_writer() -> None:
    source = EMBEDDING_HANDLER_PATH.read_text(encoding="utf-8")

    assert "frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None" in (
        source
    )
    assert "DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED" in source
    assert "DRAFT_CLAIM_EMBEDDINGS_GENERATED" in source
    assert "persisted_batch_event" in source
    assert "persisted_generated_event" in source


def test_cluster_handler_supports_frontend_projection_writer() -> None:
    source = CLUSTER_HANDLER_PATH.read_text(encoding="utf-8")

    assert "frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None" in (
        source
    )
    assert "DRAFT_CLAIM_CLUSTERS_BUILT" in source
    assert "persisted_clusters_event" in source
    assert 'operation_key": "cluster_draft_claims"' in source
    assert "DRAFT_CLAIM_CLUSTERING" in source


def test_workflow_projection_composition_is_not_claim_builder_only() -> None:
    resume_source = RESUME_COMPOSITION_PATH.read_text(encoding="utf-8")
    after_upload_source = AFTER_UPLOAD_COMPOSITION_PATH.read_text(encoding="utf-8")

    for source in (resume_source, after_upload_source):
        assert "KnowledgeExtractionFrontendWorkflowEventProjector()" in source
        assert "ClaimBuilderFrontendWorkflowEventProjector()" not in source

    composite_source = (
        PROJECTORS_DIR / "knowledge_extraction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    assert "SourceIngestionFrontendWorkflowEventProjector" in composite_source
    assert "ClaimBuilderFrontendWorkflowEventProjector" in composite_source
    assert "DraftClaimEmbeddingFrontendWorkflowEventProjector" in composite_source
    assert "DraftClaimClusterFrontendWorkflowEventProjector" in composite_source


def test_clusters_built_has_frontend_projection_coverage() -> None:
    cluster_projector_source = (
        PROJECTORS_DIR / "draft_claim_cluster_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    assert "DRAFT_CLAIM_CLUSTERS_BUILT" in cluster_projector_source
    assert "workflow_draft_claim_clusters_built" in cluster_projector_source


def test_cluster_projection_contract_is_row_availability_not_count_only() -> None:
    cluster_projector = (
        PROJECTORS_DIR / "draft_claim_cluster_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "workflow_draft_claim_clusters_built" in cluster_projector
    assert "draft_claim_cluster_rows" in cluster_projector
    assert "draft_claim_cluster_group" in cluster_projector
    assert "draft_claim_clusters_by_workflow" in cluster_projector
    assert "targeted_read" in cluster_projector
    assert "include_batches" in cluster_projector
    for forbidden_body_field in (
        "member_claims",
        "group_members",
        '"claim"',
        '"possible_questions"',
        '"exclusion_scope"',
        '"evidence_block"',
        '"source_claim_refs"',
    ):
        assert forbidden_body_field not in cluster_projector


def test_cluster_artifacts_are_loaded_by_targeted_read_contract() -> None:
    knowledge_source = KNOWLEDGE_HTTP_PATH.read_text(encoding="utf-8")
    frontend_source = (
        ROOT / "frontend" / "src" / "shared" / "api" / "modules" / "knowledge.ts"
    ).read_text(encoding="utf-8")

    assert '@router.get("/workflows/{workflow_run_id}/draft-claim-clusters")' in (
        knowledge_source
    )
    assert (
        '@router.get("/workflows/{workflow_run_id}/draft-claim-clusters/{group_ref}/members")'
        in knowledge_source
    )
    assert "list_cluster_groups_for_workflow" in knowledge_source
    assert "list_cluster_batches_for_workflow" in knowledge_source
    assert "list_cluster_members_for_group" in knowledge_source
    assert "getDraftClaimClustersByWorkflow" in frontend_source
    assert "getDraftClaimClusterMembersByWorkflow" in frontend_source


def test_cluster_rows_are_projection_only_not_canonical_events() -> None:
    workflow_definition = WORKFLOW_DEFINITION_PATH.read_text(encoding="utf-8")
    for forbidden_event in (
        "DraftClaimClusterGroupPersisted",
        "DraftClaimClusterGroupsPersisted",
        "DraftClaimClusterBatchPersisted",
        "DraftClaimClusterMemberPersisted",
    ):
        assert forbidden_event not in workflow_definition


def test_compaction_attempt_visibility_remains_later() -> None:
    cluster_projector = (
        PROJECTORS_DIR / "draft_claim_cluster_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    composite_source = (
        PROJECTORS_DIR / "knowledge_extraction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "DraftClaimCompactionAttempt" not in cluster_projector
    assert "workflow_draft_claim_compaction_attempt" not in composite_source


def test_early_claim_builder_projection_contract_is_not_count_only() -> None:
    source_ingestion = SOURCE_INGESTION_PROJECTOR_PATH.read_text(encoding="utf-8")
    scheduling = CLAIM_BUILDER_SCHEDULING_PROJECTOR_PATH.read_text(encoding="utf-8")
    dispatch = CLAIM_BUILDER_DISPATCH_PROJECTOR_PATH.read_text(encoding="utf-8")
    outcome = CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH.read_text(encoding="utf-8")

    assert "SOURCE_UNIT_CREATED" in source_ingestion
    assert "workflow_source_unit_created" in source_ingestion
    assert "source_unit_ref" in source_ingestion

    assert "CLAIM_BUILDER_WORK_ITEM_SCHEDULED" in scheduling
    assert "workflow_claim_builder_work_item_scheduled" in scheduling
    assert "work_item_id" in scheduling

    assert "CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED" in dispatch
    assert "workflow_claim_builder_dispatch_attempt_prepared" in dispatch
    assert "dispatch_attempt_id" in dispatch

    assert "draft_claims_available" in outcome
    assert "draft_claims_scope" in outcome
    assert 'targeted_read_kind": "draft_claims_by_work_item_or_source_unit"' in outcome
    assert "eligible_for_future_admission" in outcome
    assert "capacity_window_admission" in outcome
    assert "attempt_outcome" in outcome
    assert "provider_outcome" in outcome
    assert "validation_outcome" in outcome
    assert "persistence_outcome" in outcome
    assert "work_item_outcome" in outcome
    assert "targeted_read_hint" in outcome
    assert "draft_claim_observation_rows" in outcome
    assert "surface_kind" in outcome
    assert "draft_claim_observation" in outcome
    assert "targeted_read" in outcome
    assert "retry_owner" not in outcome
    assert "_validated_claims" not in outcome


def test_draft_claim_observation_rows_are_projection_only_not_canonical_events() -> (
    None
):
    workflow_definition = WORKFLOW_DEFINITION_PATH.read_text(encoding="utf-8")
    outcome = CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH.read_text(encoding="utf-8")

    assert "draft_claim_observation_rows" in outcome
    for forbidden_event in (
        "DraftClaimObservationPersisted",
        "DraftClaimObservationsPersisted",
        "DraftClaimObservationsAvailable",
    ):
        assert forbidden_event not in workflow_definition


def test_draft_claim_observation_rows_do_not_project_claim_body() -> None:
    outcome = CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH.read_text(encoding="utf-8")
    rows_start = outcome.index("def _draft_claim_observation_rows_patch(")
    rows_end = outcome.index("def _failure_patch(")
    rows_region = outcome[rows_start:rows_end]

    assert "targeted_read" in rows_region
    for forbidden_body_field in (
        '"claim"',
        '"possible_questions"',
        '"exclusion_scope"',
        '"evidence_block"',
        '"observation_refs"',
    ):
        assert forbidden_body_field not in rows_region


def test_item_retry_projection_does_not_own_capacity_reset_timing() -> None:
    outcome = CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH.read_text(encoding="utf-8")

    for forbidden_marker in (
        '"next_attempt_at"',
        '"claim_builder_next_run_after"',
        '"capacity_retry_at"',
        '"minute_reset_at"',
        '"daily_reset_at"',
        '"wait_until"',
        '"reset_at"',
    ):
        assert forbidden_marker not in outcome


def test_capacity_window_projection_boundary_is_passive_and_window_owned() -> None:
    capacity_window = CAPACITY_WINDOW_PROJECTOR_PATH.read_text(encoding="utf-8")
    claim_builder_router = (
        PROJECTORS_DIR / "claim_builder_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "workflow_capacity_window_exhausted" in capacity_window
    assert "workflow_capacity_window_scheduled_wakeup" in capacity_window
    assert "workflow_capacity_window_leased_work_item" in capacity_window
    assert "workflow_capacity_window_waiting_due_work" in capacity_window
    assert "workflow_capacity_window_admission_skipped" in capacity_window
    assert "CapacityWindowFrontendWorkflowEventProjector" in claim_builder_router

    for forbidden_marker in (
        'patch["next_attempt_at"]',
        'patch["retry_owner"]',
        'patch["work_item_retry_timer"]',
    ):
        assert forbidden_marker not in capacity_window
    assert "_FORBIDDEN_CAPACITY_OVERLAY_FIELDS" in capacity_window


def test_zero_dispatch_is_not_always_capacity_exhausted_in_prepare_handler() -> None:
    prepare_handler = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "application"
        / "sagas"
        / "handle_prepare_claim_builder_dispatch_batch_command.py"
    ).read_text(encoding="utf-8")
    phase_mapper = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "application"
        / "sagas"
        / "claim_builder_capacity_admission_phase_mapper.py"
    ).read_text(encoding="utf-8")

    assert "ClaimBuilderCapacityAdmissionPhaseMapper" in prepare_handler
    assert "CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING" in phase_mapper
    assert "CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM" in phase_mapper
    assert "CapacityAdmissionPhaseMappingDecision.ACTIVE_LEASED_WAIT" in phase_mapper
    assert "ClaimBuilderCapacityWaiting" in phase_mapper
    assert "ClaimBuilderNoFittingWorkItem" in phase_mapper
    assert "ClaimBuilderActiveLeasedWait" in phase_mapper


def test_attempt_outcome_visibility_uses_existing_projection_single_event_contract() -> (
    None
):
    outcome = CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH.read_text(encoding="utf-8")
    projector_writer = PROJECT_FRONTEND_WORKFLOW_EVENT_PATH.read_text(encoding="utf-8")

    assert "attempt_outcome" in outcome
    assert "workflow_claim_builder_attempt_outcome_classified" not in outcome
    assert (
        "def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None"
        in (projector_writer)
    )
    assert "repository.append(projected)" in projector_writer


def test_attempt_outcome_visibility_does_not_add_provider_validation_persistence_events() -> (
    None
):
    workflow_definition = WORKFLOW_DEFINITION_PATH.read_text(encoding="utf-8")
    for forbidden_event in (
        "ProviderRequestStarted",
        "ProviderExecutionCompleted",
        "OutputValidationCompleted",
        "DraftClaimsPersisted",
        "DraftClaimsPersistenceFailed",
    ):
        assert forbidden_event not in workflow_definition


def test_compaction_and_curation_events_remain_future_projection_coverage() -> None:
    composite_source = (
        PROJECTORS_DIR / "knowledge_extraction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    for marker in _FUTURE_UNCOVERED_EVENT_MARKERS:
        assert marker not in composite_source


def test_workflow_scoped_draft_claims_endpoint_matches_targeted_read_kind() -> None:
    knowledge_source = KNOWLEDGE_HTTP_PATH.read_text(encoding="utf-8")
    outcome = CLAIM_BUILDER_OUTCOME_PROJECTOR_PATH.read_text(encoding="utf-8")

    assert 'targeted_read_kind": "draft_claims_by_work_item_or_source_unit"' in outcome
    assert '@router.get("/workflows/{workflow_run_id}/draft-claims")' in (
        knowledge_source
    )
    assert "list_by_workflow_scope" in knowledge_source

    endpoint_start = knowledge_source.index("async def workflow_draft_claims(")
    endpoint_end = knowledge_source.index(
        '@router.get("/workflows/{workflow_run_id}/draft-claim-clusters")'
    )
    endpoint_region = knowledge_source[endpoint_start:endpoint_end]

    for forbidden_marker in (
        "fetch_workbench_workflow_live_state",
        "make_knowledge_extraction_workflow_resume",
        "RunKnowledgeExtractionWorkflowResumeCommand",
        "llm_runtime",
        "capacity_runtime",
        "compaction",
        "cluster",
    ):
        assert forbidden_marker not in endpoint_region


def test_patch_18c_compaction_projector_registered_and_sanitized() -> None:
    root = Path(__file__).resolve().parents[2]
    router = (
        root
        / "src/contexts/knowledge_workbench/observability/application/projectors/"
        / "knowledge_extraction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    projector = (
        root
        / "src/contexts/knowledge_workbench/observability/application/projectors/"
        / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "DraftClaimCompactionFrontendWorkflowEventProjector" in router
    assert "_draft_claim_compaction.project(event)" in router
    assert "DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED" in projector
    assert "DRAFT_CLAIM_COMPACTION_RESULT_APPLIED" in projector
    assert "_HEAVY_OUTPUT_KEYS" in projector
    assert "compacted_claims" in projector
    assert "reduced_rewrite" in projector
    assert "_FORBIDDEN_TIMER_KEYS" in projector
    assert "next_attempt_at" in projector
    assert "generated_compaction_nodes" in projector
    assert "draft_claim_compaction_nodes_by_workflow_or_group" in projector


def test_patch_18c_keeps_compaction_projection_out_of_reducer_and_curation() -> None:
    root = Path(__file__).resolve().parents[2]
    projector = (
        root
        / "src/contexts/knowledge_workbench/observability/application/projectors/"
        / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "PublishDraftClaimCurationWorkspace" not in projector
    assert "OpenDraftClaimCurationWorkspace(" not in projector
    assert "React" not in projector
    assert "workflow-live-state" not in projector


def test_patch_18d_compaction_correctness_markers_are_backend_only() -> None:
    repository_source = Path(
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_draft_claim_compaction_reduction_state_repository.py"
    ).read_text(encoding="utf-8")
    planner_source = Path(
        "src/contexts/knowledge_workbench/extraction/application/policies/"
        "draft_claim_compaction_reduction_planner_policy.py"
    ).read_text(encoding="utf-8")
    budget_source = Path(
        "src/contexts/knowledge_workbench/extraction/application/policies/"
        "draft_claim_compaction_batch_budget_policy.py"
    ).read_text(encoding="utf-8")

    assert "draft_claim_compaction_origin_separation_edges" in repository_source
    assert "origin_separation_edges" in planner_source
    assert "group.member_count == 1 or len(refs) > 1" in budget_source
    assert "frontend reducer" not in repository_source.lower()
    assert "curation" not in repository_source.lower()
    assert "publication" not in repository_source.lower()


def test_patch_18e_compaction_frontier_read_contract_is_backend_surface_not_reducer() -> (
    None
):
    knowledge_http = KNOWLEDGE_HTTP_PATH.read_text(encoding="utf-8")
    reduction_models = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "extraction"
        / "application"
        / "models"
        / "draft_claim_compaction_reduction_models.py"
    ).read_text(encoding="utf-8")
    frontend_api = (
        ROOT / "frontend" / "src" / "shared" / "api" / "modules" / "knowledge.ts"
    ).read_text(encoding="utf-8")
    docs = (
        ROOT / "docs" / "architecture" / "workflow_frontend_event_projection_map.md"
    ).read_text(
        encoding="utf-8",
    )

    assert "draft-claim-compaction-frontier" in knowledge_http
    assert "DraftClaimCompactionFrontierReadModel" in reduction_models
    assert "separation_summary" in knowledge_http
    assert "sample_origin_pairs" in knowledge_http
    assert "getDraftClaimCompactionFrontierByWorkflow" in frontend_api
    assert "does not invent ClusterBatch rows" in docs
    assert "Frontend reducer, React UI" in docs
    assert "curation, publication" in docs


def test_patch_18f_compaction_capacity_window_correlation_is_attachable_without_fake_batches() -> (
    None
):
    capacity_projector = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "observability"
        / "application"
        / "projectors"
        / "capacity_window_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    capacity_events = (
        ROOT
        / "src"
        / "contexts"
        / "knowledge_workbench"
        / "application"
        / "sagas"
        / "capacity_window_workflow_events.py"
    ).read_text(encoding="utf-8")
    docs = (
        ROOT / "docs" / "architecture" / "workflow_frontend_event_projection_map.md"
    ).read_text(encoding="utf-8")

    assert "compaction_context" in capacity_projector
    assert (
        "draft_claim_compaction_pending_work_by_workflow_or_group" in capacity_projector
    )
    assert "compaction_context_from_schedule_payload" in capacity_events
    assert "pending reduction work" in docs
    assert "fake ClusterBatch" in docs
    assert "Frontend reducer, React UI, curation, publication" in docs


def test_patch_19a_compaction_attempt_append_contract_uses_work_item_and_dispatch_attempt_keys() -> (
    None
):
    projector = (
        PROJECTORS_DIR / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert '"pending_reduction_work"' in projector
    assert '"compaction_attempt"' in projector
    assert '"row_key": work_item_id' in projector
    assert '"history_key": dispatch_attempt_id' in projector
    assert (
        '"attempts_append_under": "pending_reduction_work[work_item_id]"' in projector
    )
    assert '"attempt_history_key": "dispatch_attempt_id"' in projector


def test_patch_19a_compaction_next_work_triggers_pending_and_frontier_reads_without_fake_batch_creation() -> (
    None
):
    projector = (
        PROJECTORS_DIR / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert '"does_not_create_cluster_batch_rows": True' in projector
    assert "draft_claim_compaction_pending_work_by_workflow_or_group" in projector
    assert "draft_claim_compaction_frontier_by_workflow_or_group" in projector


def test_patch_19a_result_applied_is_generated_node_and_frontier_boundary() -> None:
    projector = (
        PROJECTORS_DIR / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert '"frontier_update"' in projector
    assert '"reason": "result_applied"' in projector
    assert '"generated_nodes_available": True' in projector
    assert "draft_claim_compaction_nodes_by_workflow_or_group" in projector
    assert "draft_claim_compaction_frontier_by_workflow_or_group" in projector


def test_patch_19a_compaction_reducer_contract_uses_explicit_attachment_fields_not_prefix_parsing() -> (
    None
):
    projector = (
        PROJECTORS_DIR / "draft_claim_compaction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "_batch_ref_from_work_item_id" not in projector

    attempt_start = projector.index("def _attempt_payload(")
    attempt_end = projector.index("def _result_applied_payload(")
    attempt_region = projector[attempt_start:attempt_end]

    contract_start = projector.index("def _compaction_entity_contract(")
    contract_end = projector.index("def _nodes_targeted_read(")
    contract_region = projector[contract_start:contract_end]

    assert "removeprefix" not in attempt_region
    assert "removeprefix" not in contract_region
    assert '"group_ref"' in projector
    assert '"batch_ref"' in projector
    assert "input_node_refs" in projector
    assert "input_claim_refs" in projector


def test_patch_19a_frontend_api_has_pending_work_targeted_read_alias() -> None:
    frontend_source = (
        ROOT / "frontend" / "src" / "shared" / "api" / "modules" / "knowledge.ts"
    ).read_text(encoding="utf-8")

    assert "getDraftClaimCompactionPendingWorkByWorkflow" in frontend_source
    assert (
        "getDraftClaimCompactionFrontierByWorkflow(projectId, workflowRunId"
        in frontend_source
    )
    assert "include_inactive: true" in frontend_source


def test_patch_19b_frontend_projection_event_client_exists() -> None:
    frontend_source = (
        ROOT / "frontend" / "src" / "shared" / "api" / "modules" / "knowledge.ts"
    ).read_text(encoding="utf-8")

    assert "FrontendWorkflowEventEnvelope" in frontend_source
    assert "FrontendWorkflowEventsResponse" in frontend_source
    assert "FrontendWorkflowEventsQuery" in frontend_source
    assert "getFrontendWorkflowEvents" in frontend_source
    assert "streamFrontendWorkflowEvents" in frontend_source
    assert "frontend-events/stream" in frontend_source
    assert "streamWorkflowLiveState" in frontend_source


def test_patch_19b_compaction_shadow_reducer_exists_and_is_pure_frontend_foundation() -> (
    None
):
    reducer_path = (
        ROOT
        / "frontend"
        / "src"
        / "pages"
        / "knowledge"
        / "shadow"
        / "compactionProjectionShadowReducer.ts"
    )
    reducer = reducer_path.read_text(encoding="utf-8")

    assert "createEmptyCompactionShadowState" in reducer
    assert "reduceCompactionProjectionEvent" in reducer
    assert "appliedProjectionEventIds" in reducer
    assert "pendingReductionWork" in reducer
    assert "capacityWindows" in reducer
    assert "targetedReadRequests" in reducer
    assert "workflow_draft_claim_compaction_result_applied" in reducer
    assert "workflow_capacity_window_leased_work_item" in reducer

    for forbidden_marker in (
        "from 'react'",
        'from "react"',
        "KnowledgeDocumentCard",
        "KnowledgePage",
        "streamWorkflowLiveState",
        "workflow-live-state",
        "fetch(",
        "authedJsonRequest",
    ):
        assert forbidden_marker not in reducer


def test_patch_19b_visible_knowledge_page_and_document_card_are_not_switched_to_projection_stream() -> (
    None
):
    page = (
        ROOT / "frontend" / "src" / "pages" / "knowledge" / "KnowledgePage.tsx"
    ).read_text(encoding="utf-8")
    card = (
        ROOT
        / "frontend"
        / "src"
        / "pages"
        / "knowledge"
        / "components"
        / "KnowledgeDocumentCard.tsx"
    ).read_text(encoding="utf-8")

    assert "streamWorkflowLiveState" in page
    assert "streamFrontendWorkflowEvents" not in page
    assert "reduceCompactionProjectionEvent" not in page
    assert "WorkbenchWorkflowLiveStateResponse" in card
    assert "CompactionShadowState" not in card


def test_workflow_state_save_updates_workbench_document_current_processing_run_id() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py"
    ).read_text(encoding="utf-8")

    assert "UPDATE knowledge_workbench_documents" in source
    assert "current_processing_run_id = $1" in source
    assert "state.workflow_run_id" in source
    assert "state.source_document_ref" in source


def test_workbench_document_delete_cleans_frontend_workflow_events() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/infrastructure/postgres/postgres_workbench_document_run_cleanup_repository.py"
    ).read_text(encoding="utf-8")

    assert "DELETE FROM frontend_workflow_events" in source
    assert "_delete_frontend_workflow_events" in source
    assert "document_id = $2" in source
    assert "workflow_run_id = ANY" in source


def test_project_clear_deletes_orphan_frontend_workflow_events() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "DELETE FROM frontend_workflow_events" in source
    assert "source-document:{project_id}:%" in source
    assert '"frontend_workflow_events"' in source
