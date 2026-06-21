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


def test_embedding_canonical_events_have_projector_modules() -> None:
    assert (
        PROJECTORS_DIR / "draft_claim_embedding_frontend_workflow_event_projector.py"
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
