from pathlib import Path


REPOSITORY_PATH = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def _publish_ready_method_source() -> str:
    source = REPOSITORY_PATH.read_text()
    return source.split(
        "async def publish_latest_reconciled_fact_registry_snapshot", 1
    )[1].split(
        "async def purge_transient_processing_workspace_after_publication", 1
    )[0]


def test_publish_ready_selection_uses_canonicalization_barrier_marker() -> None:
    method_source = _publish_ready_method_source()

    assert "fact_registry_canonicalization_barrier" in method_source
    assert "final_snapshot_id" in method_source
    assert "snapshot.entries_payload ->> 'contract' = 'fact_registry'" in method_source
    assert "snapshot.entry_count > 0" in method_source
    assert "run.status = 'completed'" in method_source


def test_publish_ready_selection_does_not_use_retired_final_reconciliation_or_prompt_c_unit_marker() -> None:
    method_source = _publish_ready_method_source()

    assert "faq_surface_final_reconciliation" not in method_source
    assert "faq_surface_registry_merge" not in method_source
    assert "artifact.metadata ->> 'snapshot_id'" not in method_source
