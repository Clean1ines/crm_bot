from pathlib import Path


def test_knowledge_upload_queue_handler_forbids_legacy_faq_path() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_upload.py").read_text(encoding="utf-8")
    assert "Legacy knowledge upload queue handler cannot process mode=faq" in source
