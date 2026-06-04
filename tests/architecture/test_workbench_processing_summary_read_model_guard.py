from pathlib import Path


DOCUMENT_LIST_SERVICE = Path("src/application/workbench_observability/document_list.py")
OBSERVABILITY_REPOSITORY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)


def test_document_list_read_model_exposes_processing_summary_without_breaking_legacy_metrics_shape() -> (
    None
):
    source = DOCUMENT_LIST_SERVICE.read_text()

    assert 'processing_summary = _mapping(row.get("processing_summary"))' in source
    assert "result_metrics: dict[str, object]" in source
    assert '"canonical_fact_count": canonical_fact_count' in source
    assert '"runtime_entry_count": runtime_entry_count' in source
    assert '"registry_retained": _bool(row.get("registry_retained"))' in source
    assert '"final_registry_snapshot_id": final_registry_snapshot_id' in source
    assert "if processing_summary:" in source


def test_document_list_read_model_exposes_durable_summary_metrics_when_present() -> (
    None
):
    source = DOCUMENT_LIST_SERVICE.read_text()

    assert '"processing_summary": processing_summary' in source
    assert '"total_prompt_tokens"' in source
    assert '"total_completion_tokens"' in source
    assert '"total_tokens"' in source
    assert '"total_llm_calls"' in source
    assert '"active_elapsed_seconds"' in source
    assert '"wall_elapsed_seconds"' in source
    assert '"published_surface_count"' in source


def test_observability_repository_selects_processing_summary_from_documents() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text()

    assert "processing_summary" in source
    assert "FROM knowledge_workbench_documents" in source
