from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_curation_action_persistence_module_owns_action_and_version_sql() -> None:
    source = _read(
        "src/infrastructure/db/repositories/knowledge_curation_action_persistence.py"
    )

    required = [
        "async def create_or_get_result_action(",
        "async def create_manual_curation_action(",
        "async def load_existing_manual_curation_action(",
        "async def write_version_snapshot(",
        "knowledge_edit_actions",
        "knowledge_entry_versions",
        "previous_snapshot",
        "new_snapshot",
        "idempotency_conflict",
    ]
    for marker in required:
        assert marker in source


def test_repository_delegates_action_persistence_helpers() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    operations_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")
    action_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_action_persistence.py"
    ).read_text(encoding="utf-8")

    repository_delegates = [
        "create_manual_curation_action(",
        "create_or_get_result_action(",
        "load_existing_manual_curation_action(",
        "mark_action_applied(",
        "mark_action_rejected(",
        "mark_action_failed(",
        "mark_action_completed_with_result(",
    ]
    for marker in repository_delegates:
        assert marker in repository_source

    operation_delegates = [
        "write_version_snapshot(",
        "mark_action_applied_raw(",
        "mark_action_in_progress_raw(",
    ]
    for marker in operation_delegates:
        assert marker in operations_source

    assert "write_version_snapshot(" not in repository_source
    assert "mark_action_in_progress_raw(" not in repository_source

    persistence_owners = [
        "async def write_version_snapshot(",
        "INSERT INTO knowledge_entry_versions",
        "async def mark_action_completed_with_result(",
        "UPDATE knowledge_edit_actions",
        "async def mark_action_applied_raw(",
        "async def mark_action_in_progress_raw(",
    ]
    for marker in persistence_owners:
        assert marker in action_persistence_source
