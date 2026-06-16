from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_http_delete_uses_application_use_case_not_inline_cleanup_sql() -> None:
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    delete_start = content.index("async def _delete_knowledge_document_by_source_ref(")
    delete_end = content.index(
        '@router.delete("/source-documents/{source_document_ref}")',
        delete_start,
    )
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


def test_clear_collects_source_document_refs_with_separate_uuid_and_text_parameters() -> (
    None
):
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    helper_start = content.index("async def _list_project_source_document_refs(")
    helper_end = content.index("def _deleted_row_count(", helper_start)
    helper_block = content[helper_start:helper_end]

    assert "knowledge_workbench_documents" in helper_block
    assert "WHERE project_id = $1::uuid" in helper_block
    assert "source_documents" in helper_block
    assert "WHERE project_id = $2::text" in helper_block
    assert "project_id,\n            project_id," in helper_block


def test_clear_deletes_orphan_workflow_runtime_tails_by_project_workflow_prefix() -> (
    None
):
    content = (ROOT / "src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "_delete_project_orphan_knowledge_runtime_tails" in content
    assert "knowledge-extraction:source-document:{project_id}:%" in content
    assert "workflow_runtime_timeline_entries" in content
    assert "workflow_runtime_command_log" in content
    assert "workflow_runtime_outbox_events" in content
    assert "workflow_runtime_progress_snapshots" in content
    assert "workflow_runtime_resource_usage_snapshots" in content
    assert "orphan_runtime_tail_counts" in content


def test_document_run_cleanup_collects_execution_work_items_from_schedule_payload() -> (
    None
):
    content = (
        ROOT / "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_workbench_document_run_cleanup_repository.py"
    ).read_text(encoding="utf-8")
    start = content.index("async def _work_item_ids(")
    end = content.index("async def _attempt_ids(", start)
    block = content[start:end]

    assert "execution_work_item_schedules" in block
    assert "payload->>'source_document_ref'" in block
    assert "payload->>'workflow_run_id'" in block
    assert "payload->>'source_unit_ref'" in block
