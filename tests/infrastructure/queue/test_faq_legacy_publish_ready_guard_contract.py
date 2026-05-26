from pathlib import Path


def test_publish_ready_queue_handler_forbids_legacy_faq_path() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_publish_ready.py").read_text(encoding="utf-8")
    assert "Legacy knowledge publish-ready handler cannot process mode=faq" in source
