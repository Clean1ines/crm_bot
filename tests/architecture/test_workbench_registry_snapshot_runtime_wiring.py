from __future__ import annotations

from pathlib import Path


QUEUE_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_queue_service.py"
)
APPLICATION_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_service.py"
)
SNAPSHOT_SERVICE = Path(
    "src/application/services/faq_workbench_registry_snapshot_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_registry_application_queue_wires_registry_snapshot_boundary_after_application() -> None:
    queue_service = _read(QUEUE_SERVICE)
    application_service = _read(APPLICATION_SERVICE)
    snapshot_service = _read(SNAPSHOT_SERVICE)

    assert "class FaqWorkbenchRegistrySnapshotService" in snapshot_service
    assert "PersistRegistrySnapshotNodeCommand" in snapshot_service
    assert "persist_registry_snapshot_node" in snapshot_service

    assert "FaqWorkbenchRegistrySnapshotService" in queue_service
    assert "PersistRegistrySnapshotNodeCommand" in queue_service
    assert "persist_registry_snapshot_node" in queue_service

    application_index = queue_service.index("apply_findings_to_registry")
    snapshot_index = queue_service.index("persist_registry_snapshot_node")
    mark_applied_index = queue_service.index(
        "mark_registry_application_queue_item_applied"
    )

    assert application_index < snapshot_index < mark_applied_index

    assert "application_result.snapshot" in queue_service
    assert "applied_registry_snapshot_id=application_result.snapshot.snapshot_id" in (
        queue_service
    )

    assert "create_registry_snapshot" not in application_service, (
        "REGISTRY_UPDATE_APPLICATION must not persist registry snapshots directly "
        "once REGISTRY_SNAPSHOT is a separate graph node."
    )

    forbidden_queue_markers = (
        "LlmJsonInvocationRequest",
        "generate_registry_merge",
        "generate_claim_observations",
        "generate_final_reconciliation",
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
        "upsert_question_registry_entries",
    )
    for marker in forbidden_queue_markers:
        assert marker not in queue_service
