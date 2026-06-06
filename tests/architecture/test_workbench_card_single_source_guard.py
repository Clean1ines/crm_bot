from pathlib import Path


DOCUMENT_CARDS = Path("src/application/workbench_observability/document_cards.py")
PROCESSING_OVERVIEW = Path(
    "src/application/workbench_observability/processing_overview.py"
)
KNOWLEDGE_PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")


def test_document_cards_adapter_uses_canonical_card_view_only() -> None:
    source = DOCUMENT_CARDS.read_text(encoding="utf-8")

    assert "with_workbench_document_card_view" in source

    forbidden = (
        "def _card_view(",
        "def _timer(",
        "def _actions(",
        "def _messages(",
        "def _recovery(",
        '"preprocessing_metrics"',
        '"structured_entries"',
        '"chunk_count"',
        'row.get("started_at")',
        'row.get("wall_elapsed_seconds")',
    )

    for marker in forbidden:
        assert marker not in source


def test_retired_processing_overview_service_is_removed() -> None:
    assert not PROCESSING_OVERVIEW.exists()


def test_knowledge_page_does_not_use_processing_overview_cards() -> None:
    source = KNOWLEDGE_PAGE.read_text(encoding="utf-8")

    forbidden = (
        "processingOverviewQuery",
        "knowledgeApi.processingOverview",
        "processing-overview",
    )

    for marker in forbidden:
        assert marker not in source
