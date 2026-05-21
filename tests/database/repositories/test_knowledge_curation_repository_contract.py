from __future__ import annotations

import inspect
from pathlib import Path

from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


REPOSITORY_SOURCE = Path(
    "src/infrastructure/db/repositories/knowledge_repository.py"
).read_text(encoding="utf-8")
SERVICE_SOURCE = Path(
    "src/application/services/knowledge_curation_service.py"
).read_text(encoding="utf-8")
ROUTE_SOURCE = Path("src/interfaces/http/knowledge_curation.py").read_text(
    encoding="utf-8"
)


def _method_source(source: str, method_name: str, next_method_name: str) -> str:
    start = source.index(f"async def {method_name}")
    end = source.index(f"async def {next_method_name}", start)
    return source[start:end]


def test_curation_status_repository_accepts_rebuild_embedding_flag() -> None:
    signature = inspect.signature(KnowledgeRepository.update_entry_status_visibility)
    assert "rebuild_embedding" in signature.parameters


def test_curation_get_document_does_not_select_removed_physical_columns() -> None:
    source = _method_source(
        REPOSITORY_SOURCE,
        "get_document_for_curation",
        "list_document_canonical_entries",
    )

    assert "kd.processing_stage" not in source
    assert "kd.chunk_count" not in source
    assert "AS canonical_entry_count" in source
    assert "AS retrieval_surface_count" in source
    assert "AS legacy_chunk_count" in source


def test_curation_rebuild_does_not_use_synthetic_action_ids() -> None:
    combined = "\n".join((REPOSITORY_SOURCE, SERVICE_SOURCE, ROUTE_SOURCE))

    assert "curation:rebuild" not in combined
    assert "manual_embedding_rebuild:" not in combined
    assert "create_manual_rebuild_embedding_action" in REPOSITORY_SOURCE
    assert "create_manual_rebuild_embedding_action" in SERVICE_SOURCE


def test_curation_idempotency_does_not_return_existing_action_for_mutation() -> None:
    from src.infrastructure.db.repositories.knowledge_curation_action_persistence import (
        create_manual_curation_action,
    )

    source = inspect.getsource(create_manual_curation_action)

    assert "idempotency_conflict" in source
    assert "idempotency_replay" in source
    assert "action_in_progress" in source
    assert "return await create_manual_curation_action" not in source


def test_curation_status_changes_remove_non_runtime_entries_from_surface() -> None:
    repository_source = inspect.getsource(KnowledgeRepository)
    operations_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")
    entry_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_entry_persistence.py"
    ).read_text(encoding="utf-8")

    source = _method_source(
        repository_source,
        "update_entry_status_visibility",
        "update_entry_content",
    )

    assert "await run_update_entry_status_visibility(" in source
    assert "delete_retrieval_surface(" not in source
    assert "UPDATE knowledge_entries" not in source
    assert "SELECT count(*) FROM knowledge_entry_source_refs" not in source

    assert "async def update_entry_status_visibility(" in operations_source
    assert "delete_retrieval_surface(" in operations_source
    assert "source_refs_required_to_publish" in operations_source

    assert "async def delete_retrieval_surface(" in entry_persistence_source
    assert "DELETE FROM knowledge_retrieval_surface" in entry_persistence_source


def test_curation_merge_apply_removes_absorbed_entries_from_surface() -> None:
    repository_source = inspect.getsource(KnowledgeRepository)
    operations_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")
    entry_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_entry_persistence.py"
    ).read_text(encoding="utf-8")

    source = _method_source(
        repository_source,
        "apply_manual_entry_merge",
        "create_manual_rebuild_embedding_action",
    )

    assert "await run_apply_manual_entry_merge(" in source
    assert "absorbed_already_merged" not in source
    assert "absorbed_version_conflict" not in source
    assert "delete_retrieval_surface(" not in source

    assert "absorbed_already_merged" in operations_source
    assert "absorbed_version_conflict" in operations_source
    assert "delete_retrieval_surface(" in operations_source

    assert "async def delete_retrieval_surface(" in entry_persistence_source
    assert "DELETE FROM knowledge_retrieval_surface" in entry_persistence_source


def test_curation_merge_apply_persists_result_payload_for_idempotent_replay() -> None:
    repository_source = inspect.getsource(KnowledgeRepository)
    operations_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")
    action_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_action_persistence.py"
    ).read_text(encoding="utf-8")

    source = _method_source(
        repository_source,
        "apply_manual_entry_merge",
        "create_manual_rebuild_embedding_action",
    )

    assert "await run_apply_manual_entry_merge(" in source
    assert "_merge_apply_result_from_payload" in source
    assert "await mark_action_completed_with_result(" in source
    assert "idempotency_replay_missing_result" not in source

    assert "idempotency_replay_missing_result" in operations_source
    assert "result_payload = $4::jsonb" not in repository_source
    assert "async def mark_action_completed_with_result(" in action_persistence_source
    assert "result_payload = $4::jsonb" in action_persistence_source
