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


def test_commercial_price_acquisition_is_not_started_by_ingestion_yet() -> None:
    combined = (
        INGESTION_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + QUEUE_HANDLER.read_text(encoding="utf-8")
    )

    assert "make_commercial_price_acquisition_service" not in combined
    assert "CommercialPriceAcquisitionPreparationService" not in combined
    assert "CommercialPriceAcquisitionService(" not in combined
    assert "MarkdownPriceAcquisitionAdapter" not in combined


def test_composition_does_not_touch_runtime_lookup_path() -> None:
    source = COMPOSITION_FILE.read_text(encoding="utf-8")

    assert "PriceLookupTool" not in source
    assert "SearchKnowledgeTool" not in source
    assert "list_published_price_facts_for_lookup" not in source
