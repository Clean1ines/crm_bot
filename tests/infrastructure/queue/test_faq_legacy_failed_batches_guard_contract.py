from pathlib import Path


def test_failed_batches_queue_handler_forbids_legacy_faq_path() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_failed_batches.py").read_text(encoding="utf-8")
    assert "Legacy knowledge failed-batches retry handler cannot process mode=faq" in source
