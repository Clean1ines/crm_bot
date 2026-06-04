from pathlib import Path


REPOSITORY_PATH = Path("src/infrastructure/db/knowledge_workbench_repository.py")
MIGRATION_PATH = Path(
    "migrations/080_create_workbench_local_claim_retrieval_surface.sql"
)
SECTION_PROCESSOR_PATH = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)
DRAIN_POLICY_PATH = Path(
    "src/domain/project_plane/knowledge_workbench/parallel_drain_policy.py"
)


def test_local_claim_retrieval_surface_table_has_vector_and_run_scoped_indexes() -> (
    None
):
    migration = MIGRATION_PATH.read_text()

    assert "knowledge_workbench_local_claim_retrieval_entries" in migration
    assert "embedding vector(384) NOT NULL" in migration
    assert "idx_kwb_local_claim_retrieval_run" in migration
    assert "idx_kwb_local_claim_retrieval_node_run" in migration
    assert "idx_kwb_local_claim_retrieval_embedding_ivfflat" in migration
    assert "idx_kwb_local_claim_retrieval_search_text_fts" in migration


def test_repository_persists_and_checks_local_claim_retrieval_surface_rows() -> None:
    source = REPOSITORY_PATH.read_text()

    assert "has_indexed_local_claim_retrieval_entries_for_node_run" in source
    assert "replace_local_claim_retrieval_entries" in source
    assert "FROM knowledge_workbench_local_claim_retrieval_entries" in source
    assert "DELETE FROM knowledge_workbench_local_claim_retrieval_entries" in source
    assert "INSERT INTO knowledge_workbench_local_claim_retrieval_entries" in source
    assert "$19::vector" in source
    assert "ON CONFLICT (entry_id) DO UPDATE SET" in source
    assert "status = 'indexed'" in source


def test_section_processor_checks_node_run_index_before_expensive_reindex() -> None:
    source = SECTION_PROCESSOR_PATH.read_text()

    assert "has_indexed_node_run" in source
    assert "CheckLocalClaimRetrievalSurfaceIndexedCommand" in source
    assert "claim_observations_node_run_id" in source
    assert "IndexDocumentLocalClaimRetrievalSurfaceCommand" in source


def test_canonicalization_barrier_depends_on_local_claim_retrieval_index_coverage() -> (
    None
):
    source = DRAIN_POLICY_PATH.read_text()

    assert "local_claim_retrieval_indexed_artifacts_total" in source
    assert (
        "local claim retrieval surface is not indexed for every Prompt A artifact"
        in source
    )
    assert "all section claim observations are indexed for retrieval" in source
