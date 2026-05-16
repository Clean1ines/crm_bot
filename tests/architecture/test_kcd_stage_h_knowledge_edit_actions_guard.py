from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage_h_migration_declares_action_audit_and_entry_versions() -> None:
    migration = _read("migrations/062_kcd_stage_h_knowledge_edit_actions.sql")

    required = [
        "CREATE TABLE IF NOT EXISTS knowledge_edit_actions",
        "CREATE TABLE IF NOT EXISTS knowledge_entry_versions",
        "source_result_id",
        "source_run_id",
        "source_question_id",
        "action_index",
        "actor_user_id",
        "action_type",
        "target_entry_id",
        "result_payload",
        "previous_snapshot",
        "new_snapshot",
        "ck_knowledge_edit_actions_status",
        "ck_knowledge_edit_actions_action_type",
    ]

    for marker in required:
        assert marker in migration


def test_stage_h_application_service_is_application_layer_only() -> None:
    service = _read("src/application/services/knowledge_edit_action_service.py")

    required = [
        "class KnowledgeEditActionService",
        "execute_result_actions",
        "attach_question_to_entry",
        "rebuild_entry_embedding",
        "run_full_rag_eval",
        "CREATE_ENTRY_FROM_FAILURE",
        "create_entry_from_failure",
        "mark_knowledge_edit_action_rejected",
        "_json_or_native",
    ]

    for marker in required:
        assert marker in service

    forbidden = [
        "from src.infrastructure",
        "import asyncpg",
        "FastAPI",
        "Depends(",
        "HTTPException",
    ]

    for marker in forbidden:
        assert marker not in service


def test_stage_h_knowledge_repository_owns_entry_mutations() -> None:
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")

    required = [
        "create_or_get_knowledge_edit_action",
        "mark_knowledge_edit_action_applied",
        "mark_knowledge_edit_action_rejected",
        "mark_knowledge_edit_action_failed",
        "attach_question_to_entry",
        "rebuild_entry_embedding",
        "knowledge_edit_actions",
        "knowledge_entry_versions",
        "knowledge_retrieval_surface",
        "embed_batch([embedding_text])",
    ]

    for marker in required:
        assert marker in repository


def test_stage_h_rag_eval_repository_exposes_action_source_loader() -> None:
    repository = _read("src/infrastructure/db/repositories/rag_eval_repository.py")

    required = [
        "load_result_action_source",
        "rr.proposed_actions",
        "rr.run_id",
        "rr.question_id",
        "q.project_id",
        "q.document_id",
    ]

    for marker in required:
        assert marker in repository


def test_stage_h_uses_existing_rag_eval_queue_type() -> None:
    service = _read("src/application/services/knowledge_edit_action_service.py")

    assert "TASK_RUN_FULL_RAG_EVAL" in service
    assert "run_full_rag_eval" in service
    assert '"mode": "full_document"' in service
    assert '"eval_mode": "retrieval_eval"' in service
