from __future__ import annotations

from pathlib import Path

REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def test_workbench_repository_owns_document_delete_transition_sql() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")
    method = source.split(
        "async def persist_document_delete_transition(",
        1,
    )[1].split(
        "async def persist_processing_cancellation_transition(",
        1,
    )[0]

    assert "UPDATE knowledge_workbench_documents" in method
    assert "status = $3" in method
    assert "deleted_at = COALESCE(deleted_at, $4)" in method

    assert "UPDATE knowledge_workbench_processing_runs" in method
    assert "ProcessingRunStatus" not in method

    assert "DELETE FROM execution_queue" in method
    assert "task_type = 'process_workbench_document'" in method
    assert "payload::jsonb ->> 'project_id' = $1" in method
    assert "payload::jsonb ->> 'document_id' = $2" in method

    assert "DELETE FROM knowledge_workbench_runtime_retrieval_entries" in method
    assert "DELETE FROM knowledge_workbench_runtime_publications" in method
    assert "UPDATE knowledge_workbench_surfaces" in method
    assert "status = 'deleted'" in method


def test_workbench_document_delete_repository_method_does_not_use_legacy_tables() -> (
    None
):
    source = REPOSITORY.read_text(encoding="utf-8")
    method = source.split(
        "async def persist_document_delete_transition(",
        1,
    )[1].split(
        "async def persist_processing_cancellation_transition(",
        1,
    )[0]

    forbidden = (
        "DELETE FROM knowledge_documents",
        "DELETE FROM knowledge_base",
        "DELETE FROM knowledge_source_chunks",
        "KnowledgeArtifactCleanupPlan",
        "cleanup_document_artifacts",
    )
    for marker in forbidden:
        assert marker not in method
