from pathlib import Path

SECTION_WORKER = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)


def test_section_processor_no_longer_builds_fact_registry_before_registry_queue() -> None:
    source = SECTION_WORKER.read_text(encoding="utf-8")

    assert "process_leased_claim_observations" in source
    assert "mark_section_batch_item_claim_observations_persisted" in source
    assert "CLAIM_OBSERVATIONS_PERSISTED" in source

    assert "registry_merge_result" not in source
    assert "source_node_run_id=registry_merge_result.node_run.node_run_id" not in source
    assert "RegistryApplicationQueueItem" not in source
    assert "create_registry_application_queue_item" not in source
    assert "mark_section_batch_item_registry_application_queued" not in source
