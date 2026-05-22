from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_FILE = ROOT / "src/interfaces/composition/commercial_price_acquisition.py"
INGESTION_SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
QUEUE_HANDLER = ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py"


def test_commercial_price_acquisition_composition_wires_infrastructure_adapters() -> (
    None
):
    source = COMPOSITION_FILE.read_text(encoding="utf-8")

    assert "CommercialPriceAcquisitionService" in source
    assert "CommercialPriceAcquisitionServicePort" in source
    assert "MarkdownPriceAcquisitionAdapter" in source
    assert "make_commercial_price_acquisition_service" in source


def test_commercial_price_acquisition_is_started_by_price_list_ingestion_only() -> None:
    ingestion_source = INGESTION_SERVICE.read_text(encoding="utf-8")
    queue_source = QUEUE_HANDLER.read_text(encoding="utf-8")

    assert "commercial_price_acquisition_service_factory" in ingestion_source
    assert "make_commercial_price_acquisition_service" in queue_source
    assert "CommercialPriceAcquisitionPreparationService" not in queue_source
    assert "MarkdownPriceAcquisitionAdapter" not in queue_source


def test_composition_does_not_touch_runtime_lookup_path() -> None:
    source = COMPOSITION_FILE.read_text(encoding="utf-8")

    assert "PriceLookupTool" not in source
    assert "SearchKnowledgeTool" not in source
    assert "list_published_price_facts_for_lookup" not in source
