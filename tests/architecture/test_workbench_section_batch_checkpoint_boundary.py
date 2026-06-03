from __future__ import annotations

from pathlib import Path


MIGRATION = Path("migrations/073_workbench_section_batch_queue.sql")
PORTS = Path("src/application/ports/knowledge_workbench.py")
REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
SERVICE = Path(
    "src/application/services/faq_workbench_section_batch_planning_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_section_batch_checkpoint_has_persistent_tables_and_repository_methods() -> (
    None
):
    parallel_migration = Path(
        "migrations/073_workbench_parallel_section_batch_queue.sql"
    ).read_text(encoding="utf-8")
    old_migration = Path("migrations/073_workbench_section_batch_queue.sql").read_text(
        encoding="utf-8"
    )
    repository = Path(
        "src/infrastructure/db/knowledge_workbench_repository.py"
    ).read_text(encoding="utf-8")
    port = Path("src/application/ports/knowledge_workbench.py").read_text(
        encoding="utf-8"
    )

    normalized_parallel_migration = " ".join(parallel_migration.lower().split())
    normalized_old_migration = " ".join(old_migration.lower().split())

    assert "knowledge_workbench_parallel_section_batch_plans" in parallel_migration
    assert "knowledge_workbench_section_batch_queue_items" in parallel_migration

    plan_schema_markers = (
        "create table if not exists knowledge_workbench_parallel_section_batch_plans",
        "batch_plan_id text primary key",
        "processing_run_id text not null",
        "project_id uuid not null",
        "document_id text not null",
        "observed_registry_snapshot_id text not null",
        "observed_registry_snapshot_sequence integer not null",
        "max_lanes integer not null",
        "lanes_payload jsonb not null",
        "queue_item_count integer not null",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz",
    )
    for marker in plan_schema_markers:
        assert marker in normalized_parallel_migration

    queue_schema_markers = (
        "create table if not exists knowledge_workbench_section_batch_queue_items",
        "queue_item_id text primary key",
        "batch_plan_id text not null references knowledge_workbench_parallel_section_batch_plans(batch_plan_id)",
        "processing_run_id text not null",
        "project_id uuid not null",
        "document_id text not null",
        "section_id text not null",
        "section_key text not null",
        "section_index integer not null",
        "lane_id text not null",
        "lane_index integer not null",
        "observed_registry_snapshot_id text not null",
        "observed_registry_snapshot_sequence integer not null",
        "status text not null",
        "claimed_by_worker_id text",
        "lease_expires_at timestamptz",
        "claim_observations_node_run_id text",
        "registry_application_queue_item_id text",
        "error_kind text",
        "attempt_count integer not null default 0",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz",
    )
    for marker in queue_schema_markers:
        assert marker in normalized_parallel_migration

    index_markers = (
        "idx_workbench_parallel_section_batch_plans_run",
        "idx_workbench_section_batch_queue_run_status",
        "idx_workbench_section_batch_queue_plan",
    )
    for marker in index_markers:
        assert marker in normalized_parallel_migration

    assert "intentionally no-op" in normalized_old_migration
    assert "create table" not in normalized_old_migration

    canonical_repository_markers = (
        "knowledge_workbench_parallel_section_batch_plans",
        "knowledge_workbench_section_batch_queue_items",
        "create_parallel_section_batch_plan",
        "list_section_batch_queue_items",
        "lease_next_ready_section_work_item",
        "restore_stale_section_work_item_leases",
    )
    for marker in canonical_repository_markers:
        assert marker in repository or marker in port

    forbidden_repository_markers = (
        "knowledge_workbench_section_batch_plans",
        "knowledge_workbench_section_work_items",
    )
    for marker in forbidden_repository_markers:
        assert marker not in repository


def test_orchestrator_uses_section_batch_checkpoint_before_legacy_sequential_loop() -> (
    None
):
    orchestrator = _read(ORCH)
    service = _read(SERVICE)

    assert "FaqWorkbenchSectionBatchPlanningService" in orchestrator
    assert "_process_parallel_section_batch_checkpoint" in orchestrator
    assert "get_latest_section_batch_plan" in orchestrator
    assert "list_section_work_items" in orchestrator
    assert "ProcessParallelSectionBatchCommand" in orchestrator
    assert "sections_to_process" in orchestrator
    assert "existing_sections_to_process" in orchestrator

    checkpoint_index = orchestrator.index(
        "await self._process_parallel_section_batch_checkpoint("
    )
    section_loop_index = orchestrator.index(
        "await self._process_sections_against_registry("
    )
    assert checkpoint_index < section_loop_index

    assert "restore_stale_section_work_item_leases" in service
    assert "ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH" in service


def test_section_batch_checkpoint_does_not_introduce_parallel_executor_or_registry_races() -> (
    None
):
    combined = _read(ORCH) + _read(SERVICE)

    forbidden = (
        "asyncio.gather",
        "create_task(",
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
    )
    for marker in forbidden:
        assert marker not in combined
