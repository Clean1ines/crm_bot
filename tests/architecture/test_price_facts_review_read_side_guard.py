from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DTO_FILE = ROOT / "src/application/dto/knowledge_dto.py"
SERVICE_FILE = ROOT / "src/application/services/knowledge_service.py"
HTTP_FILE = ROOT / "src/interfaces/http/knowledge.py"


def _slice_between(source: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    start = source.find(start_marker)
    if start == -1:
        raise AssertionError(f"start marker not found: {start_marker}")

    end_candidates = [
        source.find(marker, start + len(start_marker))
        for marker in end_markers
        if source.find(marker, start + len(start_marker)) != -1
    ]
    end = min(end_candidates) if end_candidates else len(source)
    return source[start:end]


def test_price_facts_review_read_side_has_dto_service_and_route() -> None:
    dto_source = DTO_FILE.read_text(encoding="utf-8")
    service_source = SERVICE_FILE.read_text(encoding="utf-8")
    http_source = HTTP_FILE.read_text(encoding="utf-8")

    assert "KnowledgePriceFactsResponseDto" in dto_source
    assert "async def price_facts(" in service_source
    assert '@router.get("/{document_id}/price-facts")' in http_source


def test_price_facts_review_read_side_includes_non_runtime_facts() -> None:
    service_source = SERVICE_FILE.read_text(encoding="utf-8")
    read_method = _slice_between(
        service_source,
        "    async def price_facts(",
        (
            "    async def publish_price_facts(",
            "    async def reject_price_facts(",
            "    async def cancel_document_processing(",
        ),
    )

    assert "get_price_document_by_knowledge_document" in read_method
    assert "list_price_facts_for_document" in read_method
    assert "include_non_runtime=True" in read_method


def test_price_facts_review_read_side_does_not_publish_or_touch_runtime_lookup() -> (
    None
):
    service_source = SERVICE_FILE.read_text(encoding="utf-8")
    http_source = HTTP_FILE.read_text(encoding="utf-8")
    read_method = _slice_between(
        service_source,
        "    async def price_facts(",
        (
            "    async def publish_price_facts(",
            "    async def reject_price_facts(",
            "    async def cancel_document_processing(",
        ),
    )
    read_route = _slice_between(
        http_source,
        '@router.get("/{document_id}/price-facts")',
        (
            '@router.post("/{document_id}/price-facts/publish")',
            '@router.post("/{document_id}/price-facts/reject")',
            '@router.post("/{document_id}/retighten")',
        ),
    )
    combined = read_method + "\n" + read_route

    assert "publish_price_facts(" not in combined
    assert "reject_price_facts(" not in combined
    assert "list_published_price_facts_for_lookup(" not in combined
    assert "PriceLookupTool" not in combined
