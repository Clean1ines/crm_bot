from __future__ import annotations

from pathlib import Path


def test_source_ingestion_persists_workbench_document_read_model() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/source_management/infrastructure/postgres/"
        "postgres_source_management_repository.py",
    ).read_text(encoding="utf-8")

    required = (
        "INSERT INTO source_documents",
        "INSERT INTO knowledge_workbench_documents",
        "document.document_ref.value",
        "'processing'",
        "'source_ingestion'",
        "'active_processing'",
        "deleted_at = NULL",
    )

    for marker in required:
        assert marker in source


def test_workbench_document_list_returns_file_size_for_frontend_contract() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "file_size_bytes" in source
    assert '"file_size": document.get("file_size_bytes", 0)' in source


def test_upload_visibility_bridge_does_not_restore_retired_legacy_tables() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/source_management/infrastructure/postgres/"
        "postgres_source_management_repository.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "knowledge_entries",
        "knowledge_source_chunks",
        "knowledge_retrieval_surface",
        "KnowledgeService.upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
    )

    for marker in forbidden:
        assert marker not in source
