from __future__ import annotations

import ast
from pathlib import Path


REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
PORT = Path("src/application/ports/knowledge_workbench.py")
REGISTRY_MIGRATION = Path(
    "migrations/073_create_workbench_registry_application_queue.sql"
)

CANONICAL = "knowledge_workbench_fact_registry_application_queue"
NONCANONICAL = CANONICAL + "_items"

REGISTRY_WORKER_METHODS = (
    "create_registry_application_queue_item",
    "restore_stale_registry_application_work_item_leases",
    "lease_next_ready_registry_application_work_item",
    "update_registry_application_queue_item",
    "get_parallel_processing_drain_counts",
)

OLDER_QUEUE_METHODS_STILL_ALLOWED_FOR_NOW = (
    "create_registry_application_queue_items",
    "lease_next_registry_application_queue_item",
    "mark_registry_application_queue_item_applied",
    "mark_registry_application_queue_item_waiting_for_fresh_registry",
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    source = _read(path)
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines(keepends=True)

    chunks: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            assert node.end_lineno is not None
            chunks.append("".join(lines[node.lineno - 1 : node.end_lineno]))

    assert chunks, f"{function_name} not found in {path}"
    return "\n".join(chunks)


def test_registry_application_queue_has_one_canonical_table_name_in_repo() -> None:
    source = _read(REPO)

    assert CANONICAL in source
    assert NONCANONICAL not in source


def test_registry_worker_methods_use_canonical_queue_table() -> None:
    for method_name in REGISTRY_WORKER_METHODS:
        source = _function_source(REPO, method_name)

        assert CANONICAL in source
        assert NONCANONICAL not in source


def test_older_queue_methods_share_same_canonical_table_until_service_cleanup() -> None:
    repo_source = _read(REPO)

    for method_name in OLDER_QUEUE_METHODS_STILL_ALLOWED_FOR_NOW:
        if (
            f"def {method_name}(" not in repo_source
            and f"async def {method_name}(" not in repo_source
        ):
            continue

        source = _function_source(REPO, method_name)

        assert CANONICAL in source
        assert NONCANONICAL not in source


def test_registry_application_queue_migration_defines_only_canonical_table() -> None:
    source = _read(REGISTRY_MIGRATION)

    assert f"CREATE TABLE IF NOT EXISTS {CANONICAL}" in source
    assert NONCANONICAL not in source


def test_port_exposes_registry_worker_methods_without_table_names() -> None:
    source = _read(PORT)

    for method_name in REGISTRY_WORKER_METHODS:
        assert method_name in source

    assert NONCANONICAL not in source


def test_registry_application_queue_cleanup_does_not_detour_into_lifecycle_or_legacy() -> (
    None
):
    combined = _read(REPO) + _read(PORT)

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


def test_registry_application_queue_cleanup_respects_parallel_section_batch_canon() -> (
    None
):
    source = _read(REPO)

    canonical_tables = (
        "knowledge_workbench_parallel_section_batch_plans",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_fact_registry_application_queue",
    )
    for table in canonical_tables:
        assert table in source

    noncanonical_tables = (
        "knowledge_workbench_section_batch_plans",
        "knowledge_workbench_section_work_items",
    )
    for table in noncanonical_tables:
        assert table not in source

    old_migration = Path("migrations/073_workbench_section_batch_queue.sql")
    assert old_migration.exists()
    old_migration_source = old_migration.read_text(encoding="utf-8")
    normalized_old_migration = " ".join(old_migration_source.lower().split())

    assert "intentionally no-op" in normalized_old_migration
    assert "create table" not in normalized_old_migration
