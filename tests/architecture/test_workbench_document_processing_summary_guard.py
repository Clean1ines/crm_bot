from pathlib import Path


MIGRATION = Path("migrations/081_add_workbench_document_processing_summary.sql")
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def test_workbench_documents_have_durable_processing_summary_column() -> None:
    migration = MIGRATION.read_text()

    assert "ALTER TABLE knowledge_workbench_documents" in migration
    assert "processing_summary JSONB NOT NULL DEFAULT '{}'::jsonb" in migration
    assert "idx_kwb_documents_processing_summary_gin" in migration


def test_publication_purge_persists_processing_summary_before_workspace_delete() -> (
    None
):
    source = REPOSITORY.read_text()

    assert "persist_document_processing_summary_before_purge" in source
    assert "workbench_document_processing_summary_v1" in source
    assert "processing_summary = jsonb_strip_nulls" in source

    purge_method = source.split(
        "async def purge_transient_processing_workspace_after_publication",
        1,
    )[1]
    assert "persist_document_processing_summary_before_purge" in purge_method
    assert purge_method.index(
        "persist_document_processing_summary_before_purge"
    ) < purge_method.index("DELETE FROM knowledge_workbench_processing_runs")


def test_processing_summary_keeps_required_business_metrics() -> None:
    source = REPOSITORY.read_text()

    for key in (
        "active_elapsed_seconds",
        "wall_elapsed_seconds",
        "total_prompt_tokens",
        "total_completion_tokens",
        "total_tokens",
        "total_llm_calls",
        "document_section_count",
        "prompt_a_artifact_count",
        "prompt_c_artifact_count",
        "canonical_fact_count",
        "fact_relation_count",
        "claim_observation_count",
        "registry_update_count",
        "published_surface_count",
        "published_runtime_fact_count",
        "published_at",
    ):
        assert key in source
