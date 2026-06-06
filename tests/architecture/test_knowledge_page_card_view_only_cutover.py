from pathlib import Path


PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")
CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")
DOCUMENT_CARDS = Path("src/application/workbench_observability/document_cards.py")
DEAD_BLOCK = Path("frontend/src/pages/knowledge/components/DocumentProcessingBlock.tsx")


def test_knowledge_page_does_not_import_dead_processing_block() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "DocumentProcessingBlock" not in source
    assert not DEAD_BLOCK.exists()


def test_knowledge_page_does_not_read_legacy_document_preprocessing_fields() -> None:
    source = PAGE.read_text(encoding="utf-8")

    forbidden = (
        "doc.preprocessing_metrics",
        "doc.chunk_count",
        "doc.structured_entries",
        "doc.structured_chunk_count",
        "doc.preprocessing_status",
        "doc.llm_tokens_total",
        "doc.llm_models",
        "doc.preprocessing_error",
        "doc.preprocessing_model",
        "doc.preprocessing_prompt_version",
        "preprocessing_metrics?:",
        "chunk_count:",
        "structured_entries?:",
        "structured_chunk_count?:",
        "llm_tokens_input?:",
        "llm_tokens_output?:",
        "llm_tokens_total?:",
        "llm_usage_events_count?:",
        "llm_models?:",
    )

    for marker in forbidden:
        assert marker not in source


def test_workbench_document_card_shows_active_timer_only() -> None:
    source = CARD.read_text(encoding="utf-8")

    assert "liveActiveElapsedSeconds" in source
    assert "liveWallElapsedSeconds" not in source
    assert " · всего " not in source


def test_workbench_document_list_adapter_does_not_emit_legacy_processing_payload() -> (
    None
):
    source = DOCUMENT_CARDS.read_text(encoding="utf-8")

    forbidden = (
        '"preprocessing_metrics"',
        '"structured_entries"',
        '"chunk_count"',
        "def _compat_metrics(",
        'row.get("started_at")',
        'row.get("wall_elapsed_seconds")',
    )

    for marker in forbidden:
        assert marker not in source
