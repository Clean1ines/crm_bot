from __future__ import annotations

from pathlib import Path


MIGRATION = Path("migrations/073_create_workbench_registry_application_queue.sql")
PORTS = Path("src/application/ports/knowledge_workbench.py")
REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
QUEUE_DOMAIN = Path(
    "src/domain/project_plane/knowledge_workbench/registry_application_queue.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_registry_application_queue_table_is_declared_for_resume_and_freshness() -> (
    None
):
    source = _read(MIGRATION)

    assert "knowledge_workbench_registry_application_queue" in source
    assert "observed_registry_snapshot_id" in source
    assert "observed_registry_snapshot_sequence" in source
    assert "claim_input_refs" in source
    assert "claimed_by_worker_id" in source
    assert "lease_expires_at" in source
    assert "applied_registry_snapshot_id" in source
    assert "stale_at_registry_snapshot_id" in source

    assert "idx_workbench_registry_application_queue_ready" in source
    assert "idx_workbench_registry_application_queue_snapshot" in source


def test_registry_application_queue_repository_contract_exists_without_worker_wiring() -> (
    None
):
    port_source = _read(PORTS)
    repo_source = _read(REPO)

    required = (
        "create_registry_application_queue_items",
        "lease_next_registry_application_queue_item",
        "mark_registry_application_queue_item_waiting_for_fresh_registry",
        "mark_registry_application_queue_item_applied",
        "RegistryApplicationQueueItem",
    )
    for marker in required:
        assert marker in port_source
        assert marker in repo_source

    assert "FOR UPDATE SKIP LOCKED" in repo_source
    assert "observed_registry_snapshot_sequence ASC" in repo_source


def test_registry_application_queue_persistence_does_not_create_second_registry_mutator() -> (
    None
):
    combined = _read(QUEUE_DOMAIN) + _read(PORTS) + _read(REPO)

    assert "RegistryUpdateAppliedBy.LLM_ADVISORY" not in combined
    assert "apply_findings_to_registry" not in _read(QUEUE_DOMAIN)
    assert "generate_registry_updates" not in _read(QUEUE_DOMAIN)
