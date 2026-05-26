from pathlib import Path


def test_knowledge_ingestion_service_forbids_legacy_faq_paths() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(encoding="utf-8")
    assert "Legacy knowledge ingestion preprocessor path is forbidden for mode=faq" in source
    assert "Legacy knowledge ingestion retry path is forbidden for mode=faq" in source
