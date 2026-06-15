from pathlib import Path


DELETE_SERVICE = Path("src/application/workbench_commands/delete_document.py")
CLEAR_SERVICE = Path("src/application/workbench_commands/clear_project.py")
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
FRONTEND_API = Path("frontend/src/shared/api/modules/knowledge.ts")
HTTP = Path("src/interfaces/http/knowledge.py")


def test_frontend_delete_and_clear_buttons_have_backend_routes() -> None:
    frontend = FRONTEND_API.read_text()
    http = HTTP.read_text()

    assert "deleteDocument:" in frontend
    assert "clear:" in frontend
    assert "method: 'DELETE'" in frontend
    assert '@router.delete("/{document_id}")' in http
    assert '@router.delete("")' in http
    assert "delete_workbench_document" in http
    assert "clear_workbench_project" in http


def test_delete_document_service_removes_final_retrieval_projections() -> None:
    source = DELETE_SERVICE.read_text()

    assert "cleanup_document_final_retrieval_projections" in source
    assert "runtime_publication_should_be_removed" in source


def test_clear_project_service_removes_final_retrieval_projections() -> None:
    source = CLEAR_SERVICE.read_text()

    assert "cleanup_project_final_retrieval_projections" in source
    assert "runtime_publications_should_be_removed" in source


def test_repository_cleanup_removes_durable_workbench_runtime_vectors() -> None:
    source = REPOSITORY.read_text()

    assert "cleanup_document_final_retrieval_projections" in source
    assert "cleanup_project_final_retrieval_projections" in source
    assert "DELETE FROM knowledge_workbench_runtime_retrieval_entries" in source
    assert "DELETE FROM knowledge_workbench_local_claim_retrieval_entries" in source
    assert "DELETE FROM " + "knowledge_" + "retrieval_" + "surface" in source
    assert "DELETE FROM knowledge_entries" in source
    assert "entry_kind = 'faq_workbench_fact'" in source
    assert "metadata ->> 'workbench_document_id'" in source
