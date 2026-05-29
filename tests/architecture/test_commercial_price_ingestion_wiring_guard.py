from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INGESTION_SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
STRUCTURED_SERVICE = (
    ROOT / "src/application/services/knowledge_structured_ingestion_service.py"
)
COMMERCIAL_PRICE_INGESTION_SERVICE = (
    ROOT / "src/application/services/commercial_price_ingestion_service.py"
)
QUEUE_HANDLER = ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py"


def test_price_list_ingestion_wiring_is_mode_gated() -> None:
    source = STRUCTURED_SERVICE.read_text(encoding="utf-8")

    assert "CommercialPriceIngestionService" in source
    assert "CommercialPriceRepositoryFactoryPort" in source
    assert "commercial_price_repo_factory" in source
    assert "MODE_PRICE_LIST" in source
    assert (
        "if mode == MODE_PRICE_LIST and commercial_price_repo_factory is not None"
        in source
    )


def test_price_list_ingestion_wiring_uses_dedicated_repository_from_queue_handler() -> (
    None
):
    source = QUEUE_HANDLER.read_text(encoding="utf-8")

    assert "CommercialPriceRepository" in source
    assert "CommercialPriceKnowledgePort" in source
    assert "make_commercial_price_repository" in source
    assert "commercial_price_repo_factory=make_commercial_price_repository" in source


def test_price_list_ingestion_wiring_does_not_touch_runtime_answer_path() -> None:
    combined = (
        INGESTION_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + QUEUE_HANDLER.read_text(encoding="utf-8")
    )

    assert "PriceLookupTool" not in combined
    assert "PriceLookupResult" not in combined
    assert "list_published_price_facts_for_lookup(" not in combined


def test_price_list_ingestion_logs_acquisition_summary_without_runtime_lookup() -> None:
    source = STRUCTURED_SERVICE.read_text(encoding="utf-8")

    assert "price_acquisition_row_count" in source
    assert "price_acquisition_fact_candidate_count" in source
    assert "price_acquisition_issue_count" in source
    assert "list_published_price_facts_for_lookup(" not in source


def test_price_list_ingestion_persists_review_facts_without_publishing_them() -> None:
    commercial_source = COMMERCIAL_PRICE_INGESTION_SERVICE.read_text(encoding="utf-8")
    orchestration_source = STRUCTURED_SERVICE.read_text(encoding="utf-8")
    combined = commercial_source + "\n" + orchestration_source

    assert "replace_price_facts_for_document" in commercial_source
    assert "PriceFactStatus.NEEDS_REVIEW" in commercial_source
    assert "PriceFactStatus.PUBLISHED" not in combined
    assert "publish_price_facts(" not in combined
    assert "list_published_price_facts_for_lookup(" not in combined
