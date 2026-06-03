from __future__ import annotations

from pathlib import Path


ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
QUEUE_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_queue_service.py"
)
HELPERS = Path("tests/application/workbench/helpers.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_section_processing_enqueues_registry_application_checkpoint_before_embedded_apply() -> (
    None
):
    source = _read(ORCH)

    assert "_enqueue_registry_application_queue_item_for_section" in source
    assert "RegistryApplicationQueueItem(" in source
    assert "RegistryApplicationQueueItemStatus.READY" in source
    assert "create_registry_application_queue_items" in source
    assert "mark_registry_application_queue_item_applied" in source

    merge_index = source.index("await self._persist_registry_merge_advice_for_section(")
    enqueue_index = source.index(
        "await self._enqueue_registry_application_queue_item_for_section("
    )
    apply_index = source.index(
        "await self._registry_application_service.apply_findings_to_registry("
    )
    mark_applied_index = source.index(
        "await self._repository.mark_registry_application_queue_item_applied("
    )

    assert merge_index < enqueue_index < apply_index < mark_applied_index


def test_registry_application_queue_item_captures_observed_snapshot_and_claim_input_refs() -> (
    None
):
    source = _read(ORCH)

    assert "observed_registry_snapshot_id=latest_snapshot.snapshot_id" in source
    assert (
        "observed_registry_snapshot_sequence=latest_snapshot.sequence_number" in source
    )
    assert "claim_input_refs=claim_input_refs" in source
    assert "source_node_run_id=section_claim_observations_result.node_run.node_run_id" in source
    assert 'self._id_factory.new_id("registry-application-queue-item")' in source


def test_registry_application_queue_worker_service_still_not_wired_into_document_handler() -> (
    None
):
    orchestrator_source = _read(ORCH)
    queue_service_source = _read(QUEUE_SERVICE)

    assert "class FaqWorkbenchRegistryApplicationQueueService" in queue_service_source
    assert "process_next_queue_item" in queue_service_source

    assert "FaqWorkbenchRegistryApplicationQueueService(" not in orchestrator_source
    assert "process_next_queue_item(" not in orchestrator_source


def test_shared_inmemory_workbench_repository_supports_queue_checkpoint_state() -> None:
    source = _read(HELPERS)

    assert "registry_application_queue_items" in source
    assert "create_registry_application_queue_items" in source
    assert "mark_registry_application_queue_item_applied" in source
    assert "mark_registry_application_queue_item_waiting_for_fresh_registry" in source
