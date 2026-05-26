from pathlib import Path


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_all_legacy_queue_handlers_block_faq_mode() -> None:
    upload = _source("src/infrastructure/queue/handlers/knowledge_upload.py")
    failed_batches = _source("src/infrastructure/queue/handlers/knowledge_failed_batches.py")
    retighten = _source("src/infrastructure/queue/handlers/knowledge_retighten.py")
    publish_ready = _source("src/infrastructure/queue/handlers/knowledge_publish_ready.py")

    assert "Legacy knowledge upload queue handler cannot process mode=faq" in upload
    assert "Legacy knowledge failed-batches retry handler cannot process mode=faq" in failed_batches
    assert "Legacy knowledge retighten handler cannot process mode=faq" in retighten
    assert "Legacy knowledge publish-ready handler cannot process mode=faq" in publish_ready
