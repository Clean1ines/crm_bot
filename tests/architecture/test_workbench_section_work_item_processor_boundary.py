from __future__ import annotations

from pathlib import Path


SERVICE = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)
LEASE_SERVICE = Path(
    "src/application/services/faq_workbench_section_work_item_lease_service.py"
)
REGISTRY_APP_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_section_work_item_processor_exists_as_single_item_slice() -> None:
    source = _read(SERVICE)

    assert "FaqWorkbenchSectionWorkItemProcessorService" in source
    assert "process_one_section_work_item" in source
    assert "ProcessOneSectionWorkItemCommand" in source
    assert "ProcessLeasedClaimObservationsCommand" in source
    assert "LeasedClaimObservationsRunnerPort" in source
    assert "RegistryApplicationQueueItem(" in source


def test_section_work_item_processor_loads_latest_snapshot_before_findings() -> None:
    source = _read(SERVICE)

    latest_snapshot_index = source.index("get_latest_registry_snapshot(")
    runner_index = source.index("process_leased_claim_observations(")
    registry_queue_index = source.index("RegistryApplicationQueueItem(")

    assert latest_snapshot_index < runner_index < registry_queue_index
    assert "latest_registry_snapshot=latest_registry_snapshot" in source
    assert (
        "observed_registry_snapshot_id=latest_registry_snapshot.snapshot_id" in source
    )
    assert "observed_registry_snapshot_sequence=(" in source


def test_section_work_item_processor_queues_registry_application_but_never_mutates_registry() -> (
    None
):
    source = _read(SERVICE)

    assert "create_registry_application_queue_item" in source
    assert "RegistryApplicationQueueItemStatus.READY" in source

    forbidden = (
        "RegistryUpdateAppliedBy",
        "RegistryUpdateApplication(",
        "upsert_question_registry_entries",
        "create_registry_update_applications",
        "apply_findings_to_registry",
        "LLM_ADVISORY",
    )
    for marker in forbidden:
        assert marker not in source


def test_section_work_item_processor_does_not_detour_into_resume_cancel_stop() -> None:
    source = _read(SERVICE)

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
    )
    for marker in forbidden:
        assert marker not in source


def test_lease_and_processor_are_separate_boundaries() -> None:
    lease_source = _read(LEASE_SERVICE)
    processor_source = _read(SERVICE)

    assert "claim_next_ready_section_work_item" in lease_source
    assert "process_one_section_work_item" not in lease_source

    assert "process_one_section_work_item" in processor_source
    assert "lease_next_ready_section_work_item" not in processor_source


def test_existing_deterministic_registry_application_service_remains_the_only_mutator() -> (
    None
):
    registry_app_source = _read(REGISTRY_APP_SERVICE)
    processor_source = _read(SERVICE)

    assert "RegistryUpdateAppliedBy.DETERMINISTIC_CODE" in registry_app_source
    assert "upsert_question_registry_entries" in registry_app_source
    assert "create_registry_update_applications" in registry_app_source

    assert "RegistryUpdateAppliedBy.DETERMINISTIC_CODE" not in processor_source
