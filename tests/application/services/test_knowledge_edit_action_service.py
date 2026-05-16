from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

# Stage H marker: executable KnowledgeEditAction service contract guard.


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage_h_service_executes_only_safe_action_subset() -> None:
    service = _read("src/application/services/knowledge_edit_action_service.py")

    assert "_AUTO_EXECUTABLE_ACTIONS" in service
    assert "ATTACH_QUESTION_TO_ENTRY" in service
    assert "REBUILD_EMBEDDING" in service
    assert "RERUN_EVAL" in service

    assert "_MANUAL_REVIEW_ACTIONS" in service
    assert "CREATE_ENTRY_FROM_FAILURE" in service
    assert "does not auto-execute create_entry_from_failure" in service


def test_stage_h_service_records_action_lifecycle() -> None:
    service = _read("src/application/services/knowledge_edit_action_service.py")

    required = [
        "create_or_get_knowledge_edit_action",
        "mark_knowledge_edit_action_applied",
        "mark_knowledge_edit_action_rejected",
        "mark_knowledge_edit_action_failed",
        "applied += 1",
        "rejected += 1",
        "failed += 1",
    ]

    for marker in required:
        assert marker in service


def test_stage_h_service_reads_stored_eval_actions_not_ui_payloads() -> None:
    service = _read("src/application/services/knowledge_edit_action_service.py")

    assert "load_result_action_source" in service
    assert "proposed_actions" in service
    assert '_json_or_native(source.get("proposed_actions"))' in service
    assert "execute_result_actions" in service


def test_stage_h_service_triggers_embedding_rebuild_and_eval_rerun() -> None:
    service = _read("src/application/services/knowledge_edit_action_service.py")

    assert "rebuild_entry_embedding" in service
    assert "TASK_RUN_FULL_RAG_EVAL" in service
    assert '"retrieval_limit": 5' in service
    assert '"mode": "full_document"' in service
    assert '"eval_mode": "retrieval_eval"' in service


def test_stage_h_repository_preserves_entry_version_audit() -> None:
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")

    required = [
        "knowledge_entry_versions",
        "previous_snapshot",
        "new_snapshot",
        "from_version",
        "to_version",
        "FOR UPDATE",
        "action_id",
    ]

    for marker in required:
        assert marker in repository


def test_stage_h_repository_updates_runtime_surface_not_legacy_kb() -> None:
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")

    attach_start = repository.index("async def attach_question_to_entry")
    rebuild_start = repository.index("async def rebuild_entry_embedding")
    mutation_slice = repository[attach_start:rebuild_start]

    assert "knowledge_retrieval_surface" in mutation_slice
    assert "knowledge_entries" in mutation_slice
    assert "knowledge_base" not in mutation_slice

    rebuild_slice = repository[rebuild_start:]
    assert "knowledge_retrieval_surface" in rebuild_slice
    assert "knowledge_entries" in rebuild_slice
