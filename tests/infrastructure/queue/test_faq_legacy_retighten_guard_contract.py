from pathlib import Path


def test_retighten_queue_handler_forbids_legacy_faq_path() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_retighten.py").read_text(encoding="utf-8")
    assert "Legacy knowledge retighten handler cannot process mode=faq" in source
