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
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    operations_source = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")
    entry_persistence_source = Path(
        "src/infrastructure/db/repositories/knowledge_entry_persistence.py"
    ).read_text(encoding="utf-8")

    attach_start = repository_source.index("async def attach_question_to_entry")
    rebuild_start = repository_source.index(
        "async def rebuild_entry_embedding", attach_start
    )
    attach_wrapper = repository_source[attach_start:rebuild_start]

    helper_attach_start = operations_source.index("async def attach_question_to_entry")
    helper_rebuild_start = operations_source.index(
        "async def rebuild_entry_embedding", helper_attach_start
    )
    helper_attach = operations_source[helper_attach_start:helper_rebuild_start]

    assert "await run_attach_question_to_entry(" in attach_wrapper
    assert "knowledge_base" not in attach_wrapper
    assert "knowledge_base" not in helper_attach

    assert "await update_retrieval_surface_metadata(" in helper_attach
    assert "knowledge_retrieval_surface" in entry_persistence_source
