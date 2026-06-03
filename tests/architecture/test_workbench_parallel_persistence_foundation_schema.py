from __future__ import annotations

from pathlib import Path


REGISTRY_QUEUE_MIGRATION = Path(
    "migrations/073_create_workbench_registry_application_queue.sql"
)
PARALLEL_SECTION_MIGRATION = Path(
    "migrations/073_workbench_parallel_section_batch_queue.sql"
)
REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
PORT = Path("src/application/ports/knowledge_workbench.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_registry_application_queue_has_real_migration_schema() -> None:
    source = _read(REGISTRY_QUEUE_MIGRATION)
    normalized = " ".join(source.lower().split())

    assert (
        "create table if not exists knowledge_workbench_registry_application_queue"
        in normalized
    )

    for column in (
        "queue_item_id text primary key",
        "processing_run_id text not null",
        "project_id uuid not null",
        "document_id text not null",
        "section_id text not null",
        "source_node_run_id text not null",
        "observed_registry_snapshot_id text not null",
        "observed_registry_snapshot_sequence integer not null",
        "claim_input_refs jsonb not null",
        "status text not null",
        "claimed_by_worker_id text",
        "lease_expires_at timestamptz",
        "applied_registry_snapshot_id text",
        "stale_at_registry_snapshot_id text",
        "attempt_count integer not null default 0",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz",
    ):
        assert column in normalized

    assert "create index if not exists" in normalized
    assert "knowledge_workbench_registry_application_queue" in normalized
    assert "observed_registry_snapshot_sequence" in normalized
    assert "lease_expires_at" in normalized


def test_section_queue_fk_uses_canonical_batch_plan_table() -> None:
    source = _read(PARALLEL_SECTION_MIGRATION)

    assert (
        "CREATE TABLE IF NOT EXISTS knowledge_workbench_parallel_section_batch_plans"
        in source
    )
    assert (
        "REFERENCES knowledge_workbench_parallel_section_batch_plans(batch_plan_id)"
        in source
    )


def test_repository_parallel_sql_has_matching_persistent_tables() -> None:
    registry_migration = _read(REGISTRY_QUEUE_MIGRATION)
    section_migration = _read(PARALLEL_SECTION_MIGRATION)
    repo = _read(REPO)

    canonical_tables = (
        "knowledge_workbench_parallel_section_batch_plans",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_registry_application_queue",
    )

    migrations = registry_migration + section_migration
    for table in canonical_tables:
        assert table in migrations
        assert table in repo

    assert (
        "REFERENCES knowledge_workbench_parallel_section_batch_plans(batch_plan_id)"
        in section_migration
    )

    forbidden_repo_tables = (
        "knowledge_workbench_section_batch_plans",
        "knowledge_workbench_section_work_items",
    )
    for table in forbidden_repo_tables:
        assert table not in repo

    assert "get_parallel_processing_drain_counts" in _read(PORT)


def test_workbench_port_exposes_parallel_persistence_foundation_methods() -> None:
    source = _read(PORT)

    for method in (
        "restore_stale_section_work_item_leases",
        "lease_next_ready_section_work_item",
        "restore_stale_registry_application_work_item_leases",
        "lease_next_ready_registry_application_work_item",
        "update_registry_application_queue_item",
        "get_parallel_processing_drain_counts",
    ):
        assert method in source


def test_parallel_persistence_foundation_does_not_detour_into_lifecycle_or_legacy() -> (
    None
):
    combined = (
        _read(REGISTRY_QUEUE_MIGRATION)
        + _read(PARALLEL_SECTION_MIGRATION)
        + _read(PORT)
    )

    forbidden = (
        "ENABLE_WORKBENCH_PARALLEL",
        "WORKBENCH_PARALLEL_ENABLED",
        "os.getenv",
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in combined


def test_noncanonical_section_batch_migration_is_noop_tombstone() -> None:
    old_migration = Path("migrations/073_workbench_section_batch_queue.sql")
    assert old_migration.exists()

    source = old_migration.read_text(encoding="utf-8")
    normalized = " ".join(source.lower().split())

    assert "intentionally no-op" in normalized
    assert "create table" not in normalized
    assert "knowledge_workbench_section_batch_plans" in source
    assert "knowledge_workbench_section_work_items" in source
