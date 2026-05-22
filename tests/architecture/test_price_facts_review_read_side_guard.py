from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DTO_FILE = ROOT / "src/application/dto/knowledge_dto.py"
SERVICE_FILE = ROOT / "src/application/services/knowledge_service.py"
HTTP_FILE = ROOT / "src/interfaces/http/knowledge.py"


def test_price_facts_review_read_side_has_dto_service_and_route() -> None:
    dto_source = DTO_FILE.read_text(encoding="utf-8")
    service_source = SERVICE_FILE.read_text(encoding="utf-8")
    http_source = HTTP_FILE.read_text(encoding="utf-8")

    assert "KnowledgePriceFactsResponseDto" in dto_source
    assert "async def price_facts(" in service_source
    assert '@router.get("/{document_id}/price-facts")' in http_source


def test_price_facts_review_read_side_includes_non_runtime_facts() -> None:
    service_source = SERVICE_FILE.read_text(encoding="utf-8")

    assert "get_price_document_by_knowledge_document" in service_source
    assert "list_price_facts_for_document" in service_source
    assert "include_non_runtime=True" in service_source


def test_price_facts_review_read_side_does_not_publish_or_touch_runtime_lookup() -> (
    None
):
    combined = (
        SERVICE_FILE.read_text(encoding="utf-8")
        + "\n"
        + HTTP_FILE.read_text(encoding="utf-8")
    )

    assert "publish_price_facts(" not in combined
    assert "reject_price_facts(" not in combined
    assert "list_published_price_facts_for_lookup(" not in combined
    assert "PriceLookupTool" not in combined
