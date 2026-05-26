from pathlib import Path


def test_knowledge_upload_queue_handler_routes_faq_to_service_pipeline() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_upload.py").read_text()
    assert "mode = dto.normalized_preprocessing_mode()" in source
    assert "await service.process_document(" in source
    assert "Legacy knowledge upload queue handler cannot process mode=faq" not in source
