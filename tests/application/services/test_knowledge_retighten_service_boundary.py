from __future__ import annotations

from pathlib import Path


def test_knowledge_retighten_handler_uses_retighten_service_directly() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_retighten.py").read_text(
        encoding="utf-8"
    )

    assert "KnowledgeRetightenService" in source
    assert "KnowledgeIngestionService" not in source
    assert "knowledge_ingestion_service import" in source


def test_knowledge_retighten_service_keeps_existing_mode_constant_behavior() -> None:
    source = Path("src/application/services/knowledge_retighten_service.py").read_text(
        encoding="utf-8"
    )

    assert "mode=MODE_PRICE_LIST" in source
    assert "cases=(groups[0],)" in source
    assert "for group in groups[1:]" in source


def test_knowledge_ingestion_service_keeps_only_retighten_wrapper() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    method_index = source.index("async def retighten_processed_document")
    next_method_index = source.index("async def publish_ready_answers", method_index)
    method_slice = source[method_index:next_method_index]

    assert "KnowledgeRetightenService" in method_slice
    assert (
        "return await KnowledgeRetightenService(self.pool).retighten_processed_document"
        in (method_slice)
    )
    assert "cases=(groups[0],)" not in method_slice
    assert "for group in groups[1:]" not in method_slice
