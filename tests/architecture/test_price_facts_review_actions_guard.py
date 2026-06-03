from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DTO_FILE = ROOT / "src/application/dto/knowledge_dto.py"
SERVICE_FILE = ROOT / "src/application/services/commercial_price_review_service.py"
HTTP_FILE = ROOT / "src/interfaces/http/knowledge.py"


def test_price_facts_review_actions_have_dto_service_and_routes() -> None:
    dto_source = DTO_FILE.read_text(encoding="utf-8")
    service_source = SERVICE_FILE.read_text(encoding="utf-8")
    http_source = HTTP_FILE.read_text(encoding="utf-8")

    assert "KnowledgePriceFactsMutationResultDto" in dto_source
    assert "async def publish_price_facts(" in service_source
    assert "async def reject_price_facts(" in service_source
    assert '@router.post("/{document_id}/price-facts/publish")' in http_source
    assert '@router.post("/{document_id}/price-facts/reject")' in http_source


def test_price_facts_review_actions_reload_review_side_facts_after_mutation() -> None:
    service_source = SERVICE_FILE.read_text(encoding="utf-8")

    assert "repo.publish_price_facts(" in service_source
    assert "repo.reject_price_facts(" in service_source
    assert "include_non_runtime=True" in service_source
    assert "KnowledgePriceFactsMutationResultDto.from_facts" in service_source


def test_price_facts_review_actions_do_not_call_runtime_lookup_tools() -> None:
    combined = (
        SERVICE_FILE.read_text(encoding="utf-8")
        + "\n"
        + HTTP_FILE.read_text(encoding="utf-8")
    )

    assert "list_published_price_facts_for_lookup(" not in combined
    assert "PriceLookupTool" not in combined
    assert "SearchKnowledgeTool" not in combined
