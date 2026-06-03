from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    source = _read(path)
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            assert node.end_lineno is not None
            return "".join(lines[node.lineno - 1 : node.end_lineno])

    raise AssertionError(f"{function_name} not found in {path}")


def test_db_repository_exposes_atomic_section_work_item_lease_methods() -> None:
    source = _read(REPOSITORY)

    assert "async def restore_stale_section_work_item_leases(" in source
    assert "async def lease_next_ready_section_work_item(" in source
    assert "SectionBatchQueueItem" in source
    assert "SectionBatchQueueItemStatus" in source


def test_lease_next_ready_section_work_item_uses_postgres_skip_locked() -> None:
    source = _function_source(REPOSITORY, "lease_next_ready_section_work_item")

    assert "FOR UPDATE SKIP LOCKED" in source
    assert "LIMIT 1" in source
    assert "status = 'ready'" in source
    assert "status = 'leased'" in source
    assert "attempt_count = item.attempt_count + 1" in source
    assert "_optional_workbench_transaction" in source


def test_restore_stale_section_work_item_leases_only_releases_expired_leases() -> None:
    source = _function_source(REPOSITORY, "restore_stale_section_work_item_leases")

    assert "status = 'leased'" in source
    assert "lease_expires_at IS NOT NULL" in source
    assert "lease_expires_at <= $4" in source
    assert "claimed_by_worker_id = NULL" in source
    assert "status = 'ready'" in source


def test_section_work_item_leasing_does_not_mutate_registry_or_call_llm() -> None:
    combined = _function_source(
        REPOSITORY, "restore_stale_section_work_item_leases"
    ) + _function_source(REPOSITORY, "lease_next_ready_section_work_item")

    forbidden = (
        "upsert_question_registry_entries",
        "create_registry_update_applications",
        "RegistryUpdateAppliedBy",
        "generate_registry_updates",
        "generate_final_reconciliation",
        "invoke_json",
        "Groq",
        "AsyncGroq",
    )
    for marker in forbidden:
        assert marker not in combined
