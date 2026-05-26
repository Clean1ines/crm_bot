from pathlib import Path


def test_legacy_queue_handlers_block_faq_except_upload_router() -> None:
    upload = Path("src/infrastructure/queue/handlers/knowledge_upload.py").read_text()
    failed_batches = Path("src/infrastructure/queue/handlers/knowledge_failed_batches.py").read_text()
    retighten = Path("src/infrastructure/queue/handlers/knowledge_retighten.py").read_text()
    publish_ready = Path("src/infrastructure/queue/handlers/knowledge_publish_ready.py").read_text()

    assert "Legacy knowledge upload queue handler cannot process mode=faq" not in upload
    assert "Legacy knowledge failed-batches retry handler cannot process mode=faq" in failed_batches
    assert "Legacy knowledge retighten handler cannot process mode=faq" in retighten
    assert "Legacy knowledge publish-ready handler cannot process mode=faq" in publish_ready
