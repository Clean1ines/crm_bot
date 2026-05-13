from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PORT = ROOT / "src/application/ports/knowledge_port.py"
REPO = ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"
SERVICE = ROOT / "src/application/services/knowledge_service.py"
HTTP = ROOT / "src/interfaces/http/knowledge.py"
INGESTION = ROOT / "src/application/services/knowledge_ingestion_service.py"
FRONTEND_API = ROOT / "frontend/src/shared/api/modules/knowledge.ts"
FRONTEND_PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cancel_processing_backend_contract_is_wired() -> None:
    port = _source(PORT)
    repo = _source(REPO)
    service = _source(SERVICE)
    http = _source(HTTP)

    assert "cancel_document_processing" in port
    assert "is_document_processing_cancelled" in port
    assert "async def cancel_document_processing(" in repo
    assert "async def is_document_processing_cancelled(" in repo
    assert "payload->>'document_id'" in repo
    assert "knowledge_compiler_runs" in repo
    assert "KNOWLEDGE_PROCESSING_CANCELLED_MESSAGE" in service
    assert '@router.post("/{document_id}/cancel")' in http


def test_cancel_processing_worker_is_cooperative_between_llm_batches() -> None:
    source = _source(INGESTION)

    assert "KCD_STAGE_K_CANCELLED_ERROR" in source
    assert "await repo.is_document_processing_cancelled(document_id)" in source
    assert (
        "for batch_index, technical_chunks in enumerate(technical_batches, start=1)"
        in source
    )


def test_cancel_processing_frontend_button_is_wired() -> None:
    api = _source(FRONTEND_API)
    page = _source(FRONTEND_PAGE)

    assert "cancel: (projectId: string, documentId: string)" in api
    assert "/knowledge/${documentId}/cancel" in api
    assert "cancelProcessingMutation" in page
    assert "cancelProcessingMutation.mutate(doc.id)" in page
    assert "Остановить обработку" in page
    assert "StopCircle" in page
