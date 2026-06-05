from pathlib import Path


OBSERVABILITY_REPOSITORY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)
DOCUMENT_CARDS = Path("src/application/workbench_observability/document_cards.py")
APP = Path("src/interfaces/http/app.py")


def test_observability_document_list_selects_card_view_source_fields() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")

    required_markers = (
        "knowledge_workbench_documents",
        "knowledge_workbench_processing_runs",
        "knowledge_workbench_document_sections",
        "knowledge_workbench_fact_registries",
        "knowledge_workbench_canonical_facts",
        "knowledge_workbench_registry_snapshots",
        "knowledge_workbench_runtime_retrieval_entries",
        "section_count",
        "canonical_fact_count",
        "runtime_entry_count",
        "processing_status",
        "processing_last_error_kind",
        "processing_last_user_message",
    )

    for marker in required_markers:
        assert marker in source

    forbidden_markers = (
        "surface_summary.ready_count",
        "surface_summary.draft_count",
        "surface_summary.published_count",
        "surface_summary.rejected_count",
        "FROM knowledge_workbench_surfaces",
        "JOIN knowledge_workbench_surfaces",
    )

    for marker in forbidden_markers:
        assert marker not in source


def test_document_card_builder_exposes_frontend_required_card_view_fields() -> None:
    source = DOCUMENT_CARDS.read_text(encoding="utf-8")

    required_markers = (
        '"id"',
        '"document_id"',
        '"file_name"',
        '"file_size"',
        '"file_size_bytes"',
        '"preprocessing_status"',
        '"card_view"',
        '"actions"',
        '"timer"',
        '"usage"',
        '"sections"',
        '"registry"',
        '"runtime"',
        '"recovery"',
        '"messages"',
        '"error"',
        '"metadata"',
    )

    for marker in required_markers:
        assert marker in source


def test_fastapi_app_registers_workbench_card_list_before_legacy_knowledge_router() -> (
    None
):
    source = APP.read_text(encoding="utf-8")

    explicit_route = '@app.get("/api/projects/{project_id}/knowledge")'
    include_router = "app.include_router(knowledge_router"

    assert explicit_route in source
    assert include_router in source
    assert source.index(explicit_route) < source.index(include_router)
