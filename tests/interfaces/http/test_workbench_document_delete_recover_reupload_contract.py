from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_http_delete_uses_application_use_case_not_inline_cleanup_sql() -> None:
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    delete_start = content.index("async def _delete_knowledge_document_by_source_ref(")
    delete_end = content.index('@router.delete("")', delete_start)
    delete_block = content[delete_start:delete_end]

    assert "DeleteKnowledgeExtractionDocumentRunCommand" in delete_block
    assert "PostgresWorkbenchDocumentRunCleanupRepository" in delete_block
    assert "information_schema.columns" not in delete_block
    assert "DELETE FROM workflow_runtime_timeline_entries" not in delete_block


def test_resume_processing_alias_targets_source_document_restore() -> None:
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    assert '@router.post("/{document_id}/resume-processing")' in content
    assert "restore_knowledge_source_document_processing" in content


def test_stop_is_pause_not_delete() -> None:
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    stop_start = content.index("async def stop_knowledge_source_document_processing(")
    stop_end = content.index(
        '@router.post("/source-documents/{source_document_ref}/restore")',
        stop_start,
    )
    stop_block = content[stop_start:stop_end]
    assert "pause_knowledge_extraction_workflow" in stop_block
    assert "DeleteKnowledgeExtractionDocumentRun" not in stop_block


def test_clear_knowledge_uses_full_document_run_cleanup() -> None:
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    clear_start = content.index('@router.delete("")')
    clear_end = content.index(
        '@router.post("/workflows/{workflow_run_id}/pause")', clear_start
    )
    clear_block = content[clear_start:clear_end]

    assert "_list_project_source_document_refs" in clear_block
    assert "DeleteKnowledgeExtractionDocumentRunCommand" in clear_block
    assert "PostgresWorkbenchDocumentRunCleanupRepository" in clear_block
    assert "clear_workbench_project" not in clear_block
    assert "faq_workbench_clear" not in clear_block
    assert "workflow_run_ids" in clear_block
    assert "deleted_counts" in clear_block
