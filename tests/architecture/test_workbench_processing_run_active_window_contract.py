from pathlib import Path


DOMAIN = Path("src/domain/project_plane/knowledge_workbench/processing.py")
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
CARD_QUERY = Path("src/interfaces/composition/faq_workbench_document_cards.py")
PROJECTION = Path("src/application/workbench/document_card_projection.py")
CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")


def test_processing_run_domain_carries_current_active_window() -> None:
    source = DOMAIN.read_text()

    assert "current_active_started_at: datetime | None = None" in source


def test_repository_opens_and_closes_processing_run_active_window() -> None:
    source = REPOSITORY.read_text()

    assert "current_active_started_at" in source
    assert "persist_processing_manual_resume_transition" in source
    assert "current_active_started_at = now()" in source
    assert "current_active_started_at = NULL" in source
    assert "active_elapsed_seconds =" in source
    assert "EXTRACT(EPOCH FROM (now() - current_active_started_at))" in source


def test_production_card_query_reads_real_current_active_window() -> None:
    source = CARD_QUERY.read_text()

    assert "pr.current_active_started_at AS current_active_started_at" in source


def test_projection_does_not_use_started_at_as_active_window() -> None:
    source = PROJECTION.read_text()
    current_active_context = source[
        source.index("current_started_at") : source.index(
            "return WorkbenchDocumentCardSource"
        )
    ]

    assert "current_active_started_at" in current_active_context
    assert 'row.get("started_at")' not in current_active_context


def test_frontend_timer_has_no_fake_doc_updated_at_fallback() -> None:
    source = CARD.read_text()

    assert "fallbackTimerStartedAtMs" not in source
    assert "doc.updated_at || null" not in source
