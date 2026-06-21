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


def test_compaction_and_curation_events_remain_future_projection_coverage() -> None:
    composite_source = (
        PROJECTORS_DIR / "knowledge_extraction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    for marker in _FUTURE_UNCOVERED_EVENT_MARKERS:
        assert marker not in composite_source
