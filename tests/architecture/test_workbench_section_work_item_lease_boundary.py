from __future__ import annotations

from pathlib import Path


SERVICE = Path(
    "src/application/services/faq_workbench_section_work_item_lease_service.py"
)
DOMAIN_QUEUE = Path(
    "src/domain/project_plane/knowledge_workbench/section_batch_queue.py"
)
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_section_work_item_lease_service_exists_as_worker_boundary_not_executor() -> (
    None
):
    source = _read(SERVICE)

    assert "FaqWorkbenchSectionWorkItemLeaseService" in source
    assert "ClaimSectionWorkItemCommand" in source
    assert "claim_next_ready_section_work_item" in source
    assert "restore_stale_section_work_item_leases" in source
    assert "lease_next_ready_section_work_item" in source
    assert "SectionBatchQueueItem" in source

    forbidden = (
        "asyncio.gather",
        "asyncio.create_task",
        "TaskGroup",
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
    )
    for marker in forbidden:
        assert marker not in source


def test_section_work_item_lease_boundary_does_not_mutate_registry() -> None:
    source = _read(SERVICE)

    forbidden = (
        "RegistryUpdateAppliedBy",
        "RegistryUpdateApplication",
        "upsert_question_registry_entries",
        "create_registry_update_applications",
        "apply_findings_to_registry",
        "LLM_ADVISORY",
    )
    for marker in forbidden:
        assert marker not in source


def test_section_work_item_lease_boundary_does_not_detour_into_lifecycle_actions() -> (
    None
):
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


def test_section_work_item_lease_is_not_wired_into_orchestrator_yet() -> None:
    source = _read(ORCH)

    assert "FaqWorkbenchSectionWorkItemLeaseService" not in source
    assert "claim_next_ready_section_work_item" not in source


def test_section_batch_domain_still_owns_lease_state_transition() -> None:
    source = _read(DOMAIN_QUEUE)

    assert "SectionBatchQueueItemStatus.LEASED" in source
    assert "mark_section_batch_item_leased" in source
    assert "claimed_by_worker_id" in source
    assert "lease_expires_at" in source
