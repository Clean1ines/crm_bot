from __future__ import annotations

from pathlib import Path


def test_knowledge_list_fallback_never_hides_source_ingestion_documents_without_card_view() -> (
    None
):
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "_workbench_document_card_view_fallback(document)" in source
    assert '"card_view": None' not in source
    assert "source_unit_count" in source
    assert "cancel_processing" in source
    assert "delete_document" in source


def test_frontend_card_component_still_requires_card_view_so_backend_must_supply_it() -> (
    None
):
    source = Path(
        "frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx",
    ).read_text(encoding="utf-8")

    assert "if (!cardView)" in source
    assert "return null" in source
