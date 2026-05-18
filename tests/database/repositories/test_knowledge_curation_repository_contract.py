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
    source = _method_source(
        REPOSITORY_SOURCE,
        "_create_manual_curation_action",
        "update_entry_status_visibility",
    )

    assert 'return str(existing["id"])' not in source
    assert "idempotency_replay" in source
    assert "action_in_progress" in source
    assert "idempotency_conflict" in source


def test_curation_status_changes_remove_non_runtime_entries_from_surface() -> None:
    source = _method_source(
        REPOSITORY_SOURCE,
        "update_entry_status_visibility",
        "update_entry_content",
    )

    assert "DELETE FROM knowledge_retrieval_surface WHERE entry_id = $1" in source
    assert "source_refs_required_to_publish" in source


def test_curation_merge_apply_removes_absorbed_entries_from_surface() -> None:
    source = _method_source(
        REPOSITORY_SOURCE,
        "apply_manual_entry_merge",
        "create_manual_rebuild_embedding_action",
    )

    assert "DELETE FROM knowledge_retrieval_surface WHERE entry_id = $1" in source
    assert "absorbed_already_merged" in source
    assert "absorbed_version_conflict" in source
    assert "parent_version_conflict" in source


def test_curation_merge_apply_persists_result_payload_for_idempotent_replay() -> None:
    source = _method_source(
        REPOSITORY_SOURCE,
        "apply_manual_entry_merge",
        "create_manual_rebuild_embedding_action",
    )

    assert "_load_existing_manual_curation_action" in source
    assert "_merge_apply_result_from_payload" in REPOSITORY_SOURCE
    assert "_manual_merge_action_payload" in REPOSITORY_SOURCE
    assert "idempotency_replay_missing_result" in source
    assert "result_payload = $4::jsonb" in source
    assert "applied_with_warning" in source
    assert "replayed=False" in source
    assert "replayed=True" in REPOSITORY_SOURCE
