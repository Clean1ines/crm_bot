from pathlib import Path


REPOSITORY_PATH = Path("src/infrastructure/db/knowledge_workbench_repository.py")
BARRIER_SERVICE_PATH = Path(
    "src/application/services/faq_workbench_canonicalization_barrier_service.py"
)


def test_canonicalization_completion_guard_uses_document_level_barrier_marker() -> None:
    source = REPOSITORY_PATH.read_text()

    assert "fact_registry_canonicalization_barrier" in source
    assert "knowledge_workbench_registry_snapshots AS snapshot" in source
    assert "marker.metadata ->> 'final_snapshot_id'" in source
    assert "snapshot.entries_payload ->> 'contract' = 'fact_registry'" in source
    assert "snapshot.entry_count >= 0" in source


def test_canonicalization_completion_guard_does_not_use_single_prompt_c_unit_artifact() -> (
    None
):
    source = REPOSITORY_PATH.read_text()
    method_source = source.split(
        "async def has_completed_fact_registry_canonicalization", 1
    )[1].split("async def get_parallel_processing_drain_counts", 1)[0]

    assert "fact_registry_canonicalization'" not in method_source
    assert "faq_surface_registry_merge" not in method_source
    assert "node_run.status = 'completed'" not in method_source


def test_canonicalization_barrier_persists_completion_marker_after_all_units() -> None:
    source = BARRIER_SERVICE_PATH.read_text()

    assert "_persist_canonicalization_barrier_completion_marker" in source
    assert "expected_unit_count=retrieval_result.unit_count" in source
    assert "completed_unit_count=prompt_c_success_count" in source
    assert "final_snapshot_id=previous_snapshot_id" in source
    assert '"contract": "fact_registry_canonicalization_barrier"' in source
