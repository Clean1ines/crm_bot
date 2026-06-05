from pathlib import Path


PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")
PROCESSING_OVERVIEW = Path(
    "src/application/workbench_observability/processing_overview.py"
)


def test_knowledge_page_uses_get_knowledge_as_only_document_card_source() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "const documents = baseDocuments;" in source
    assert "overviewDocuments" not in source
    assert "processingOverviewQuery.data?.documents" not in source
    assert (
        "overviewDocuments.length > 0 ? overviewDocuments : baseDocuments" not in source
    )


def test_processing_overview_does_not_return_document_cards() -> None:
    source = PROCESSING_OVERVIEW.read_text(encoding="utf-8")

    assert '"documents": documents' not in source
    assert '"items": documents' not in source
    assert '"active_document_ids"' in source
    assert '"failed_document_ids"' in source
    assert '"resumable_document_ids"' in source
