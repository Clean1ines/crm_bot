from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_active_delete_recover_paths_do_not_use_retired_legacy_tables_or_services() -> (
    None
):
    paths = [
        "src/interfaces/http/knowledge.py",
        "src/contexts/knowledge_workbench/application/sagas/delete_knowledge_extraction_document_run.py",
        "src/contexts/knowledge_workbench/infrastructure/postgres/postgres_workbench_document_run_cleanup_repository.py",
        "frontend/src/shared/api/modules/knowledge.ts",
        "frontend/src/pages/knowledge/KnowledgePage.tsx",
        "frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx",
    ]
    forbidden = [
        "KnowledgeService.upload",
        "faq_workbench_document_cards",
        "knowledge_entries",
        "knowledge_source_chunks",
        "knowledge_retrieval_surface",
        "KnowledgeDocumentCurationModal",
        "window.location.reload",
        "location.reload",
    ]
    for path in paths:
        content = read(path)
        for marker in forbidden:
            assert marker not in content, f"{marker} leaked into {path}"


def test_frontend_uses_source_document_delete_stop_restore_contract() -> None:
    api = read("frontend/src/shared/api/modules/knowledge.ts")
    assert "source-documents" in api
    assert "encodeURIComponent(documentId)" in api
    assert "/stop" in api
    assert "/restore" in api
    assert "/knowledge/${documentId}`" not in api
    assert "/knowledge/${documentId}/cancel" not in api
    assert "/knowledge/${documentId}/resume-processing" not in api


def test_backend_has_source_document_delete_stop_restore_routes() -> None:
    http = read("src/interfaces/http/knowledge.py")
    assert '@router.delete("/source-documents/{source_document_ref}")' in http
    assert '@router.post("/source-documents/{source_document_ref}/stop")' in http
    assert '@router.post("/source-documents/{source_document_ref}/restore")' in http


def test_delete_contract_cleans_workflow_runtime_trace() -> None:
    repo = read(
        "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_workbench_document_run_cleanup_repository.py"
    )
    assert "workflow_runtime_timeline_entries" in repo
    assert "workflow_runtime_command_log" in repo
    assert "workflow_runtime_outbox_events" in repo
    assert "workflow_runtime_progress_snapshots" in repo
    assert "workflow_runtime_resource_usage_snapshots" in repo
