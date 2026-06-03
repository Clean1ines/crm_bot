from __future__ import annotations

from pathlib import Path


PORT = Path("src/application/ports/knowledge_workbench.py")
REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
HELPER = Path("tests/application/workbench/helpers.py")
MIGRATION = Path("migrations/073_workbench_parallel_section_batch_queue.sql")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_section_batch_queue_has_application_port_and_repository_methods() -> (
    None
):
    port_source = _read(PORT)
    repo_source = _read(REPO)
    helper_source = _read(HELPER)

    assert "KnowledgeWorkbenchSectionBatchQueueRepositoryPort" in port_source
    assert "create_parallel_section_batch_plan" in port_source
    assert "list_section_batch_queue_items" in port_source
    assert "update_section_batch_queue_item" in port_source

    assert "KnowledgeWorkbenchSectionBatchQueueRepositoryPort" in repo_source
    assert "async def create_parallel_section_batch_plan" in repo_source
    assert "async def list_section_batch_queue_items" in repo_source
    assert "async def update_section_batch_queue_item" in repo_source

    assert "section_batch_plans" in helper_source
    assert "section_batch_queue_items" in helper_source


def test_parallel_section_batch_queue_migration_creates_durable_checkpoint_tables() -> (
    None
):
    migration_source = _read(MIGRATION)

    assert "knowledge_workbench_parallel_section_batch_plans" in migration_source
    assert "knowledge_workbench_section_batch_queue_items" in migration_source
    assert "observed_registry_snapshot_id" in migration_source
    assert "observed_registry_snapshot_sequence" in migration_source
    assert "lane_id" in migration_source
    assert "claim_observations_node_run_id" in migration_source
    assert "registry_application_queue_item_id" in migration_source


def test_parallel_section_batch_persistence_does_not_detour_into_lifecycle_actions() -> (
    None
):
    combined = _read(PORT) + _read(REPO) + _read(HELPER)

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
    )
    for marker in forbidden:
        assert marker not in combined
